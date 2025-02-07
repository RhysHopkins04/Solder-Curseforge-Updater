# run.py, Entrypoint for applicaiton
from gui import start_gui
from main import main

if __name__ == "__main__":
    start_gui(main)