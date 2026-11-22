import os
import sys
import logging
import tempfile


def _setup_runtime():
    # A windowed (no-console) exe has sys.stdout / sys.stderr set to None.
    # Libraries that print or draw progress bars (tqdm, onnxruntime, numba,
    # model downloads) then raise errors inside background threads.
    # Point both at a null device so they stay harmless.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    # Log errors to a file next to the exe so problems can be diagnosed.
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    for folder in (base, tempfile.gettempdir()):
        try:
            logging.basicConfig(
                filename=os.path.join(folder, "passportstudio.log"),
                level=logging.WARNING,
                format="%(asctime)s %(levelname)s %(message)s",
            )
            break
        except OSError:
            continue


_setup_runtime()

from ui.main_window import PassportStudioApp  # noqa: E402


def main():
    app = PassportStudioApp()
    app.mainloop()


if __name__ == "__main__":
    main()