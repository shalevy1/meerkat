"""Startup script for interactive Meerkat.

Code is heavily borrowed from Gradio.
"""

import atexit
import fnmatch
import os
import pathlib
import re
import socket
import subprocess
import time
from tempfile import mkstemp

import rich
from uvicorn import Config

from meerkat.interactive.api import MeerkatAPI
from meerkat.interactive.server import (
    INITIAL_PORT_VALUE,
    LOCALHOST_NAME,
    TRY_NUM_PORTS,
    Server,
)
from meerkat.interactive.tunneling import setup_tunnel
from meerkat.state import NetworkInfo, state


def file_find_replace(directory, find, replace, pattern):
    for path, _, files in os.walk(os.path.abspath(directory)):
        for filename in fnmatch.filter(files, pattern):
            filepath = os.path.join(path, filename)
            with open(filepath) as f:
                s = f.read()
            s = s.replace(find, replace)
            with open(filepath, "w") as f:
                f.write(s)


def is_notebook() -> bool:
    """Check if the current environment is a notebook.

    Taken from
    https://stackoverflow.com/questions/15411967/how-can-i-check-if-code-is-executed-in-the-ipython-notebook.
    """
    try:
        shell = get_ipython().__class__.__name__
        if shell == "ZMQInteractiveShell":
            return True  # Jupyter notebook or qtconsole
        elif shell == "TerminalInteractiveShell":
            return False  # Terminal running IPython
        else:
            return False  # Other type (?)
    except NameError:
        return False  # Probably standard Python interpreter


def get_first_available_port(initial: int, final: int) -> int:
    """Gets the first open port in a specified range of port numbers. Taken
    from https://github.com/gradio-app/gradio/blob/main/gradio/networking.py.

    New solution:
    https://stackoverflow.com/questions/19196105/how-to-check-if-a-network-port-is-open

    Args:
        initial: the initial value in the range of port numbers
        final: final (exclusive) value in the range of port numbers,
            should be greater than `initial`
    Returns:
        port: the first open port in the range
    """
    rich.print(f"Trying to find an open port in ({initial}, {final}). ", end="")
    for port in range(initial, final):
        try:
            s = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            )  # create a socket object
            result = s.bind((LOCALHOST_NAME, port))  # Bind to the port
            s.close()
            rich.print(f"Found open port: {port}")
            return port
        except OSError:
            pass

    raise OSError(
        "All ports from {} to {} are in use. Please close a port.".format(
            initial, final - 1
        )
    )


def start(
    shareable: bool = False,
    subdomain: str = None,
    api_server_name: str = None,
    api_port: int = None,
    npm_port: int = None,
    dev: bool = True,
):
    """Start a Meerkat interactive server.

    Args:
        shareable (bool): whether to share the interface at a publicly accesible link.
            This feature works by establishing a reverse SSH tunnel to a Meerkat server.
            Do not use this feature with private data. In order to use this feature, you
            will need an SSH key for the server. If you already have one, add it to the
            file at f"{config.system.ssh_identity_file}, or set the option
            `mk.config.system.ssh_identity_file` to the file where they are stored. If
            you don't yet have a key, you can request access by emailing
            eyuboglu@stanford.edu. Remember to ensure after downloading it that the
            identity file is read/write only by the user (e.g. with
            `chmod 600 path/to/id_file`). See `subdomain` arg for controlling the
            domain name of the shared link. Defaults to False.
        subdomain (str): the subdomain to use for the shared link. For example, if
            `subdomain="myinterface"`, then the shareable link will have the domain
            `myinterface.meerkat.wiki`. Defaults to None, in which case a random
            subdomain will be generated.
        api_port (int): the port to use for the Meerkat API server. Defaults to None,
            in which case a random port will be used.
        npm_port (int): the port to use for the Meerkat Vite server. Defaults to None,
            in which case a random port will be used.
    """
    if subdomain is None:
        subdomain = "app"

    api_server_name = api_server_name or LOCALHOST_NAME

    # if port is not specified, search for first available port
    if api_port is None:
        api_port = get_first_available_port(
            INITIAL_PORT_VALUE, INITIAL_PORT_VALUE + TRY_NUM_PORTS
        )
    else:
        api_port = get_first_available_port(api_port, api_port + TRY_NUM_PORTS)

    # Start the FastAPI server
    api_server = Server(
        Config(MeerkatAPI, port=api_port, host=api_server_name, log_level="warning")
    )
    api_server.run_in_thread()

    # Start the npm server
    if npm_port is None:
        npm_port = get_first_available_port(api_port + 1, api_port + 1 + TRY_NUM_PORTS)
    else:
        npm_port = get_first_available_port(npm_port, npm_port + 1)

    # Enter the "app/" directory
    from meerkat.constants import APP_DIR

    libpath = APP_DIR  # pathlib.Path(__file__).parent.resolve() / "app"
    currdir = os.getcwd()
    os.chdir(libpath)

    network_info = NetworkInfo(
        api=MeerkatAPI,
        api_server=api_server,
        api_server_name=api_server_name,
        api_server_port=api_port,
        npm_server_port=npm_port,
    )

    if shareable:
        domain = setup_tunnel(
            network_info.api_server_port, subdomain=f"{subdomain}server"
        )
        network_info.shareable_api_server_name = domain

    # npm run dev -- --port {npm_port}
    current_env = os.environ.copy()
    if shareable:
        current_env.update({"VITE_API_URL": network_info.shareable_api_server_url})
    else:
        current_env.update({"VITE_API_URL": network_info.api_server_url})

    # open a temporary file to write the output of the npm process
    out_file, out_path = mkstemp(suffix=".out")
    err_file, err_path = mkstemp(suffix=".err")

    if dev:

        # KG: this is fallback code because we previously noticed that the
        # socket.bind call in the get_first_available_port function was not
        # always working. I've changed that to use the socket.connect_ex
        # method, which should be more reliable, but I'm leaving this code
        # here in case we need it again.
        for i in range(TRY_NUM_PORTS):
            rich.print("Trying port:", npm_port + i, end="\r")

            # Run the npm server in dev mode
            # KG: Ideally, this should work on the first go
            npm_process = subprocess.Popen(
                [
                    "npm",
                    "run",
                    "dev",
                    "--",
                    "--port",
                    str(npm_port + i),
                    "--strictPort",
                    "true",
                    "--logLevel",
                    "info",
                ],
                env=current_env,
                stdout=out_file,
                # stderr=err_file,
            )
            network_info.npm_process = npm_process
            network_info.npm_out_path = out_path
            network_info.npm_err_path = err_path

            # We need to wait for the npm server to start up
            # When it does, we read its stdout to get the port it's using

            # KG: this should no longer be required, since we now use the
            # --strictPort flag for vite, which will not allow vite
            # to automatically select a port if the one we specify is not
            # available.
            MAX_WAIT = 100  # 10 seconds total
            for _ in range(MAX_WAIT):
                time.sleep(0.1)

                # this is a hack to address the issue that the vite skips over a port that we
                # deem to be open per `get_first_available_port`
                # TODO: remove this once we figure out how to properly check for unavailable
                # ports in a way that is compatible with vite's port selection logic
                match = re.search(
                    "Local:   http:\/\/(127\.0\.0\.1|localhost):(.*)/",  # noqa: W605
                    network_info.npm_server_out,
                )
                if match is not None:
                    break

            if match is not None:
                break
            rich.print()

    else:
        # Run the npm server in build mode
        rich.print("Building Application...")
        p = subprocess.Popen(
            [
                "npm",
                "run",
                "build",
            ],
            env=current_env,
            stdout=subprocess.PIPE,
            stderr=err_file,
        )
        while p.poll() is None:
            out = p.stdout.readline()
            rich.print(out, end="\r")
        rich.print()

        # find + replace VITE_API_URL_PLACEHOLDER for production
        buildpath = libpath / "build"
        file_find_replace(
            buildpath,
            "meerkat-api-url?!?!?!?!",
            network_info.shareable_api_server_url
            if shareable
            else network_info.api_server_url,
            "*.js",
        )

        # Run the statically built app with a simple python server
        os.chdir(buildpath)
        npm_process = subprocess.Popen(
            [
                "python",
                "-m",
                "http.server",
                str(npm_port),
            ],
            env=current_env,
            stdout=out_file,
            stderr=err_file,
        )
        os.chdir(libpath)

    network_info.npm_process = npm_process
    network_info.npm_out_path = out_path
    network_info.npm_err_path = err_path

    if dev:
        if match is None:
            raise ValueError(
                f"Failed to start dev server: "
                f"out={network_info.npm_server_out} err={network_info.npm_server_err}"
            )
        network_info.npm_server_port = int(match.group(2))
    else:
        network_info.npm_server_port = npm_port

    if shareable:
        domain = setup_tunnel(network_info.npm_server_port, subdomain=subdomain)
        network_info.shareable_npm_server_name = domain

    # Back to the original directory
    os.chdir(currdir)

    # Store in global state
    state.network_info = network_info

    # Print a message
    rich.print(
        "Meerkat interactive mode started! API docs on "
        f"{network_info.api_docs_url} "
        f"and GUI server on {network_info.npm_server_url}."
    )
    return network_info


def cleanup():
    if state.network_info is not None:
        rich.print("Cleaning up [bold violet]Meerkat[/bold violet]...")
        # Shut down servers
        state.network_info.api_server.close()
        state.network_info.npm_process.terminate()
        state.network_info.npm_process.wait()

        # Delete SvelteKit routes for all interfaces
        for _, interface in state.identifiables.interfaces.items():
            interface._remove_svelte()


# Run this when the program exits
atexit.register(cleanup)


def output_startup_message(url: str):
    meerkat_header = "[bold violet]\[Meerkat][/bold violet]"  # noqa: W605

    rich.print("")
    rich.print(
        f"{meerkat_header} [bold green]➜[/bold green] [bold] Open interface at: "
        f"[/bold] [turqoise] {url} [/turqoise]"
    )
    rich.print(
        f"{meerkat_header} [bold green]➜[/bold green] [bold] Interact with Meerkat "
        " programatically with the console below. Use [yellow]quit()[/yellow] to end "
        "session. [/bold]"
    )
    rich.print("")
