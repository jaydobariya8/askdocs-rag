import subprocess
import sys


def main():
    backend = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
        ]
    )
    frontend = subprocess.Popen(
        [
            sys.executable, "-m", "streamlit",
            "run", "frontend/app.py",
            "--server.port", "8501",
        ]
    )

    try:
        backend.wait()
        frontend.wait()
    except KeyboardInterrupt:
        print("\nShutting down…")
        backend.terminate()
        frontend.terminate()


if __name__ == "__main__":
    main()
