import asyncio
import os
import shlex
import subprocess
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass

try:
    import docker
except ImportError:
    docker = None

@dataclass
class ExecResult:
    """【执行结果容器】封装输出、错误和退出码"""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False

class Sandbox(ABC):
    """【沙箱基类】定义统一的执行协议"""
    
    @abstractmethod
    async def exec(self, command: str, timeout: float = 30.0, cwd: Optional[str] = None) -> ExecResult:
        """执行一段当前系统 Shell 指令并返回结果"""
        pass

    @abstractmethod
    def map_path(self, host_path: str) -> str:
        """将物理机路径映射为沙箱内路径"""
        pass

class LocalSandbox(Sandbox):
    """【本地执行器】在宿主机执行命令；它不提供容器级隔离"""
    
    async def exec(self, command: str, timeout: float = 30.0, cwd: Optional[str] = None) -> ExecResult:
        # 在 Windows 上使用 cmd，在 Unix 上使用 sh
        shell = ["cmd", "/c"] if os.name == "nt" else ["sh", "-c"]
        
        try:
            if os.name == "nt":
                # WindowsSelectorEventLoop 不支持 asyncio 子进程 API。
                # 所以 Windows 下把阻塞式 subprocess.run 放到线程池里执行，
                # 既保留异步接口，又能稳定拿到 stdout/stderr。
                loop = asyncio.get_running_loop()

                def run_command():
                    return subprocess.run(
                        command,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=cwd,
                        timeout=timeout
                    )

                try:
                    completed = await loop.run_in_executor(None, run_command)
                    return ExecResult(
                        stdout=completed.stdout.decode(errors="replace")[-32768:],
                        stderr=completed.stderr.decode(errors="replace")[-32768:],
                        exit_code=completed.returncode
                    )
                except subprocess.TimeoutExpired as e:
                    stdout = e.stdout.decode(errors="replace")[-32768:] if e.stdout else ""
                    stderr = e.stderr.decode(errors="replace")[-32768:] if e.stderr else ""
                    return ExecResult(
                        stdout=stdout,
                        stderr=stderr or "[Timeout] Command exceeded limits",
                        exit_code=-1,
                        timed_out=True
                    )

            # 使用 asyncio.create_subprocess_exec 实现带超时的异步执行
            process = await asyncio.create_subprocess_exec(
                *shell, command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd, # 【关键注入】：锁定进程的起始目录
                # 在 Unix 上开启进程组，方便批量 kill
                preexec_fn=os.setsid if os.name != "nt" else None
            )
            
            try:
                # 核心：带超时的等待
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), 
                    timeout=timeout
                )
                return ExecResult(
                    stdout=stdout_bytes.decode(errors="replace")[-32768:], # 截断尾部 32KB
                    stderr=stderr_bytes.decode(errors="replace")[-32768:],
                    exit_code=process.returncode or 0
                )
            except asyncio.TimeoutError:
                # 超时处理：杀掉进程
                if os.name == "nt":
                    # Windows 用 taskkill
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True)
                else:
                    # Unix 用进程组信号
                    import signal
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                return ExecResult(stdout="", stderr="[Timeout] Command exceeded limits", exit_code=-1, timed_out=True)
                
        except Exception as e:
            return ExecResult(stdout="", stderr=str(e), exit_code=-1)

    def map_path(self, host_path: str) -> str:
        return os.path.abspath(host_path)

class DockerSandbox(Sandbox):
    """【Docker 沙箱】将指令投射到容器内执行"""
    
    def __init__(self, container_name: str, workspace_root: str = "/workspace"):
        if not docker:
            raise RuntimeError("请先安装 docker 库: pip install docker")
        self.client = docker.from_env()
        self.container_name = container_name
        self.workspace_root = workspace_root

    async def exec(self, command: str, timeout: float = 30.0) -> ExecResult:
        try:
            # 找到对应的容器
            container = self.client.containers.get(self.container_name)
            
            # 在 Docker SDK 中，exec_run 是同步的，我们用用 run_in_executor 包装
            loop = asyncio.get_running_loop()
            
            # 使用 sh -c 包裹指令，支持管道等复杂语法
            full_command = f"sh -c {shlex.quote(command)}"
            
            # 这是一个阻塞调用，我们通过 loop 运行它
            exit_code, output = await loop.run_in_executor(
                None, 
                lambda: container.exec_run(full_command, workdir=self.workspace_root)
            )
            
            # Docker 不需要手动 kill，因为 exec 进程随通信断开或超时而消亡
            return ExecResult(
                stdout=output.decode(errors="replace")[-32768:], 
                stderr="", 
                exit_code=exit_code
            )
        except Exception as e:
            return ExecResult(stdout="", stderr=f"[Docker Error] {str(e)}", exit_code=-1)

    def map_path(self, host_path: str) -> str:
        # 在 Docker 模式下，所有的工作都在 /workspace 中
        return self.workspace_root
