"""A connection to one open OpticStudio window.

ZOS-API calls run on a single STA thread. The user opens Interactive
Extension first. An instance number of 0 attaches to whichever window is
waiting. The installation is located through Zemax's own helper. When that
cannot find OpticStudio, set OPTICSTUDIO_DIRECTORY to the installation
directory.
"""

import ctypes
import os
import queue
import threading
import winreg

# ZOS-API is a COM object and must be called from the thread that created it.
_COINIT_APARTMENTTHREADED = 2

#: OpticStudio release this server supports.
SUPPORTED_RELEASE: str = "2024 R2"

__all__ = [
    "OpticStudioError",
    "OpticStudioSession",
    "SUPPORTED_RELEASE",
]


class OpticStudioError(Exception):
    """OpticStudio could not be located or used."""


class OpticStudioSession:
    """
    Own one Interactive Extension connection and the thread that calls it.

    :param int instance: OpticStudio instance number. ``0`` attaches to whichever window is waiting.
    :param str directory: Installation directory. When omitted, Zemax's helper locates it, then ``OPTICSTUDIO_DIRECTORY`` is used.
    :raises OpticStudioError: OpticStudio cannot be located, or the connection fails.
    """

    def __init__(self, instance: int = 0, directory: str | None = None):
        #: OpticStudio instance number. ``0`` attaches to whichever window is waiting.
        self.instance: int = instance
        #: Installation directory passed to this session.
        #: ``None`` means Zemax's helper locates OpticStudio, then ``OPTICSTUDIO_DIRECTORY`` is used.
        self.directory: str | None = directory
        # The queue, thread, and ZOS-API objects are usable only on this session's thread.
        self._jobs = queue.Queue()
        self._ready = threading.Event()
        self._startup_error = None
        self._closed = False
        self._application = None
        self._system = None
        self._thread = threading.Thread(target=self._run, name="zos-api")

        self._thread.start()
        self._ready.wait()

        if self._startup_error is not None:
            self._closed = True
            self._thread.join()
            raise self._startup_error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

        # False means an exception from the with-block still propagates.
        return False

    def close(self):
        """
        Disconnect from Interactive Extension and stop the ZOS-API thread.

        Calling this again does nothing.
        """

        if self._closed:
            return

        self._closed = True
        self._jobs.put(None)
        self._thread.join()

    def system_file(self):
        """
        Return the file path of the lens open in the OpticStudio window.

        :returns: The lens file path. An unsaved system returns an empty string.
        :rtype: str
        :raises OpticStudioError: The session is already closed.
        """

        # SystemFile is the path of the lens open in the OpticStudio window.
        return self._call(lambda: str(self._system.SystemFile))

    def _call(self, function):
        # Hand function to the ZOS-API thread and wait for its result.
        if self._closed:
            raise OpticStudioError("The OpticStudio session is closed.")

        done = queue.Queue(maxsize=1)
        self._jobs.put((function, done))
        ok, value = done.get()

        if not ok:
            raise value

        return value

    def _run(self):
        # Body of the ZOS-API thread: connect, then run queued calls until close.
        try:
            _initialize_sta()
            self._connect()
        except Exception as exc:
            self._startup_error = exc
            self._close_application()
            self._ready.set()

            return

        self._ready.set()

        try:
            while True:
                item = self._jobs.get()

                if item is None:
                    break

                function, done = item

                try:
                    done.put((True, function()))
                except Exception as exc:
                    done.put((False, exc))
        finally:
            self._close_application()
            ctypes.windll.ole32.CoUninitialize()

    def _connect(self):
        import pythonnet

        # ZOS-API is built on .NET Framework, so pythonnet must load that runtime.
        pythonnet.load("netfx")

        import clr

        # NetHelper locates the OpticStudio installation. It ships in the Zemax data folder.
        clr.AddReference(_net_helper_path())

        directory = _locate_opticstudio(self.directory)
        _require_supported_release(directory)

        # These two assemblies are the ZOS-API itself, loaded from that installation.
        clr.AddReference(os.path.join(directory, "ZOSAPI.dll"))
        clr.AddReference(os.path.join(directory, "ZOSAPI_Interfaces.dll"))

        import ZOSAPI

        connection = ZOSAPI.ZOSAPI_Connection()

        if connection is None:
            raise OpticStudioError("Unable to initialize the ZOS-API connection.")

        # Attach to the Interactive Extension dialog the user already opened.
        # Instance 0 means whichever waiting window is available.
        application = connection.ConnectAsExtension(self.instance)

        if application is None:
            raise OpticStudioError("Unable to acquire the OpticStudio application.")

        # The open seat must include a license that allows ZOS-API use.
        if not application.IsValidLicenseForAPI:
            application.CloseApplication()
            raise OpticStudioError("The license is not valid for the ZOS-API.")

        # PrimarySystem is the lens currently displayed in that window.
        system = application.PrimarySystem

        if system is None:
            application.CloseApplication()
            raise OpticStudioError("Unable to acquire the primary system.")

        self._application = application
        self._system = system

    def _close_application(self):
        application = self._application
        self._application = None
        self._system = None

        if application is not None:
            # For an Interactive Extension this ends the external connection.
            application.CloseApplication()


def _initialize_sta():
    # Mark this thread as the COM apartment that will own the ZOS-API objects.
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    ole32.CoInitializeEx.restype = ctypes.c_long
    result = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)

    if result < 0:
        raise OpticStudioError("The ZOS-API thread could not join an STA.")


def _locate_opticstudio(directory):
    import ZOSAPI_NetHelper

    # Initialize() asks NetHelper where OpticStudio is installed.
    initializer = ZOSAPI_NetHelper.ZOSAPI_Initializer

    if directory:
        if not initializer.Initialize(directory):
            raise OpticStudioError(f"Unable to initialize OpticStudio at {directory}.")
    elif not initializer.Initialize():
        directory = os.environ.get("OPTICSTUDIO_DIRECTORY")

        if not directory:
            raise OpticStudioError(
                "Unable to locate OpticStudio. Set OPTICSTUDIO_DIRECTORY to the installation directory."
            )

        if not initializer.Initialize(directory):
            raise OpticStudioError(f"Unable to initialize OpticStudio at {directory}.")

    return str(initializer.GetZemaxDirectory())


def _require_supported_release(directory):
    import System.Diagnostics

    executable = os.path.join(directory, "OpticStudio.exe")
    info = System.Diagnostics.FileVersionInfo.GetVersionInfo(executable)
    numbers = str(info.ProductVersion).split(".")

    if numbers[:2] != ["24", "2"]:
        raise OpticStudioError(
            f"OpticStudio {SUPPORTED_RELEASE} is the supported release. Found {info.ProductVersion}."
        )


def _net_helper_path():
    # ZemaxRoot is the data folder OpticStudio created, not the program directory.
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Zemax")

    try:
        root, _value_type = winreg.QueryValueEx(key, "ZemaxRoot")
    finally:
        winreg.CloseKey(key)

    # "ZemaxData" folder under installation directory of zemax
    return os.path.join(root, "ZOS-API", "Libraries", "ZOSAPI_NetHelper.dll")
