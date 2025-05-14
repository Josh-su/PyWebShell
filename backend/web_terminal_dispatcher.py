# backend/web_terminal_dispatcher.py
# This script acts as a simple command dispatcher for the web terminal.
# It presents a menu of allowed applications and launches them as child processes.

import os
import sys
import subprocess

# Configuration
# Key: command string displayed to user. Value: (script_relative_path, [arguments])
# script_relative_path is relative to CWD set by websocket_server.py.
ALLOWED_COMMANDS = {
    "python app/mindmap.py": ("backend/apps/mindmap_cli/main.py", ["--interactive-for-websocket"])
}
PYTHON_EXECUTABLE = sys.executable
# For numbered shortcuts. Assumes Python 3.7+ (ordered dicts).
ordered_command_keys = list(ALLOWED_COMMANDS.keys())


def clear_screen_and_home_cursor():
    """Prints ANSI escape codes to clear the screen and move cursor to top-left."""
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def launch_application(user_input: str):
    """
    Validates the user's command (either full string or number) and attempts to execute
    the corresponding application as a child process, waiting for it to complete.
    """
    command_to_execute_key = None

    # Attempt to interpret input as a number first
    try:
        choice_num = int(user_input)
        if 1 <= choice_num <= len(ordered_command_keys):
            command_to_execute_key = ordered_command_keys[choice_num - 1]
            print(f"Launching: {command_to_execute_key}") # Echo selected command
        else:
            print(f"Error: Invalid choice number '{choice_num}'. Please select from 1 to {len(ordered_command_keys)}.", file=sys.stderr)
            sys.stderr.flush()
            return False
    except ValueError:
        # Not a number, assume it's a full command string
        if user_input in ALLOWED_COMMANDS:
            command_to_execute_key = user_input
            print(f"Launching: {user_input}") # Echo selected command

    if command_to_execute_key is None or command_to_execute_key not in ALLOWED_COMMANDS:
        print(f"Error: Command or choice '{user_input}' is not recognized or allowed.", file=sys.stderr)
        sys.stderr.flush()
        return False

    # CWD is set by websocket_server.py to its own directory (mindmap-web-demo).
    # script_relative_path is relative to this CWD.
    script_relative_path, script_args = ALLOWED_COMMANDS[command_to_execute_key]
    full_script_path = os.path.abspath(script_relative_path)

    # Validate script path
    if not os.path.isfile(full_script_path):
        print(f"Error: Application script '{full_script_path}' not found on server.", file=sys.stderr)
        sys.stderr.flush()
        return False

    # Prepare arguments for subprocess.run
    run_args = [PYTHON_EXECUTABLE, full_script_path] + script_args

    try:
        clear_screen_and_home_cursor() # Clear screen before launching app
        sys.stdout.flush()
        sys.stderr.flush()

        # Run the application as a child process.
        # stdio is inherited from this dispatcher process.
        process = subprocess.run(
            run_args,
            check=False # Don't raise an exception for non-zero exit codes.
        )
        return True # Indicate that the app ran (or attempted to run).
    except OSError as e:
        print(f"Critical Error: Could not execute application for '{command_to_execute_key}'. Reason: {e}", file=sys.stderr)
        sys.stderr.flush()
        return False

def print_menu():
    """Prints the menu of available commands."""
    print("You can run the following applications:")
    if not ordered_command_keys:
        print("  (No applications configured)")
        sys.stdout.flush()
        return
    for i, cmd_key in enumerate(ordered_command_keys):
        print(f"  [{i+1}] {cmd_key}")
    print(f"Type the number (1-{len(ordered_command_keys)}) or the full command string.")
    print("Type 'exit' or 'quit' to close the terminal.")
    sys.stdout.flush()


if __name__ == "__main__":
    clear_screen_and_home_cursor() # Clear screen on initial dispatcher start
    print("Welcome to the MindMap Web Terminal.")
    print_menu()

    while True:
        # Display the prompt
        try:
            prompt_options = []
            if ordered_command_keys:
                prompt_options.append(f"1-{len(ordered_command_keys)}")
            prompt_options.append("cmd")
            prompt_options.append("exit")
            prompt = f"web-shell ({', '.join(prompt_options)})> "
            command_line = input(prompt) # input() will get data from the WebSocket via stdin
            command_line = command_line.strip()

            if command_line.lower() in ["exit", "quit"]:
                print("Exiting web terminal dispatcher...")
                sys.stdout.flush()
                break
            launched = launch_application(command_line)
            if launched:
                clear_screen_and_home_cursor() # Clear screen after app finishes
                print("\nApplication session ended. Returning to web-shell.")
                print_menu()

        except EOFError:
            print("\nConnection closed by client.", file=sys.stderr)
            sys.stderr.flush()
            break
        except KeyboardInterrupt: # Should ideally be handled by the connected main.py
            print("\nDispatcher interrupted. Exiting.", file=sys.stderr)
            sys.stderr.flush()
            break
        except Exception as e:
            print(f"An unexpected error occurred in the dispatcher: {e}", file=sys.stderr)
            sys.stderr.flush()
            break
    sys.exit(0)