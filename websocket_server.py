# websocket_server.py
# This script runs a FastAPI WebSocket server that launches a terminal dispatcher
# (web_terminal_dispatcher.py) as a subprocess. It streams I/O between the
# WebSocket client and the dispatcher, allowing users to interact with
# allowed command-line applications through a web interface.

import asyncio
import os
import sys
import subprocess
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles # For serving frontend static files

# Determine the directory where this script is located.
# This is used as the base for other paths and as the CWD for the subprocess.
current_script_dir = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()

# Path to the web terminal dispatcher script, assumed to be in the 'backend' subdirectory.
PATH_TO_DISPATCHER_PY = os.path.join(current_script_dir, "backend", "web_terminal_dispatcher.py")
PYTHON_EXECUTABLE = sys.executable # Use the same python interpreter

async def stream_subprocess_io(websocket: WebSocket, process: subprocess.Popen):
    """Helper to stream IO between WebSocket and subprocess."""
    loop = asyncio.get_running_loop()

    async def forward_stdin():
        try:
            # Forward data from WebSocket to the subprocess's stdin.
            while True:
                data = await websocket.receive_text()
                if process.stdin and not process.stdin.closed:
                    # Write and flush to stdin in a non-blocking way for the event loop.
                    await loop.run_in_executor(
                        None, lambda: (process.stdin.write(data.encode()), process.stdin.flush())
                    )
                else:
                    break
        except WebSocketDisconnect:
            print("Client disconnected (stdin).")
        except Exception as e:
            print(f"Stdin forwarding error: {e}")
        # Note: process.stdin is typically closed by the subprocess itself upon completion or specific command.

    async def forward_stream_to_ws(stream, stream_name: str):
        try:
            # Forward data from a subprocess stream (stdout/stderr) to the WebSocket.
            while True:
                # Read from the synchronous stream in a non-blocking way.
                line_bytes = await loop.run_in_executor(None, stream.readline)
                if not line_bytes: # EOF
                    break
                # Send decoded data to WebSocket, replacing errors to prevent crashes.
                await websocket.send_text(line_bytes.decode(errors='replace'))
            print(f"{stream_name} stream ended.")
        except WebSocketDisconnect:
            print(f"Client disconnected ({stream_name}).")
        except Exception as e:
            print(f"Error forwarding {stream_name}: {e}")

    # Create tasks for handling stdin, stdout, and stderr concurrently.
    stdin_task = asyncio.create_task(forward_stdin())
    stdout_task = asyncio.create_task(forward_stream_to_ws(process.stdout, "stdout"))
    stderr_task = asyncio.create_task(forward_stream_to_ws(process.stderr, "stderr"))

    try:
        # Wait for all I/O forwarding tasks to complete.
        # These tasks will typically end when the subprocess closes its pipes or if the WebSocket disconnects.
        await asyncio.gather(stdin_task, stdout_task, stderr_task)
    except WebSocketDisconnect:
        print("WebSocket disconnected during process IO.")
    finally:
        # Cleanup: Cancel any tasks that are still running.
        for task in [stdin_task, stdout_task, stderr_task]:
            if not task.done():
                task.cancel()
        # Ensure the subprocess is terminated if it's still running.
        if process.returncode is None:
            try:
                print("Terminating subprocess due to WebSocket closure or error.")
                process.terminate()
                await loop.run_in_executor(None, process.wait, 5.0) # Wait with timeout.
            except subprocess.TimeoutExpired:
                print("Subprocess terminate timed out, killing.")
                process.kill()
                await loop.run_in_executor(None, process.wait)
            except Exception as e_term:
                print(f"Error during subprocess termination: {e_term}")

        # Final wait to clean up subprocess resources if it hasn't exited yet.
        if process.returncode is None: await loop.run_in_executor(None, process.wait)
        print(f"Subprocess exited with {process.returncode if process.returncode is not None else 'unknown (was killed or error)'}")

@app.websocket("/ws")
async def websocket_terminal_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"WebSocket connection accepted from: {websocket.client}")

    try:
        # Command to run the web terminal dispatcher script.
        command = [PYTHON_EXECUTABLE, PATH_TO_DISPATCHER_PY]

        # Launch the dispatcher as a subprocess.
        # subprocess.Popen is blocking, so run it in a thread pool executor.
        loop = asyncio.get_running_loop()
        process = await loop.run_in_executor(
            None,  # Use default ThreadPoolExecutor.
            lambda: subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=current_script_dir, # Run dispatcher in this script's directory.
            )
        )
        print(f"Started subprocess for {websocket.client} with PID {process.pid}")

        await stream_subprocess_io(websocket, process)

    except WebSocketDisconnect:
        print(f"Client {websocket.client} disconnected.")
    except Exception as e:
        import traceback
        print(f"Error in WebSocket endpoint: {e}\n{traceback.format_exc()}")
        # Attempt to close the WebSocket connection gracefully if an error occurs.
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass # Connection might already be closed.
    finally:
        print(f"WebSocket connection with {websocket.client} processing finished.")

# Serve frontend static files (e.g., index.html, CSS, JS).
# Assumes a 'frontend' directory located as a sibling to this script's directory.
PATH_TO_FRONTEND_STATIC = os.path.join(current_script_dir, "frontend")
if os.path.exists(PATH_TO_FRONTEND_STATIC):
    app.mount("/", StaticFiles(directory=PATH_TO_FRONTEND_STATIC, html=True), name="static_frontend")
else:
    # Fallback if the frontend directory is not found.
    print(f"Warning: Frontend static directory not found at {PATH_TO_FRONTEND_STATIC}")
    @app.get("/")
    async def root_placeholder():
        return {"message": "MindMap WebSocket Server is running. Frontend not found."}


if __name__ == "__main__":
    # This block executes when the script is run directly (e.g., `python websocket_server.py`).
    # It starts the Uvicorn server programmatically.
    
    import uvicorn
    uvicorn.run(
        "websocket_server:app", # app_module:app_instance_name
        host="0.0.0.0",
        port=8000,
        reload=True # Enable reloader
    )