pyinstaller --onefile verify.py
pyinstaller --onefile setup-dedicated.py
pyinstaller --onefile run-dedicated.py
pyinstaller --onefile run-insecure.py
pyinstaller --onefile setup-listen.py
pyinstaller --onefile run-listen.py
pyinstaller --onefile run-mapping.py