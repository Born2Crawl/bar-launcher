# bar-launcher
Simple Python launcher/updater for Beyond All Reason (BAR)

## Steps build and run the launcher

### 1. Create a virtual environment and install required libraries

```bash
python3 -m venv bar_venv
source bar_venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

For Ubuntu, you'll have to install wxPython with apt:
```bash
apt-get install python3-wxgtk4.0
```

### 2. Run the script
```bash
python3 Beyond-All-Reason.py
```

### 3. Build the executable
```bash
pyinstaller -y --clean --onefile --icon resources/icon.ico Beyond-All-Reason.py
```

### 4. Update MD5 hashes for the build executables
Linux/MacOS:
```bash
cd ./dist/ && md5sum Beyond-All-Reason* > dist.md5 && cd ..
```

### 5. Copy and run the executable
Linux/MacOS:
```bash
cp ./dist/Beyond-All-Reason .
./Beyond-All-Reason
```

Windows:
```bash
cp ./dist/Beyond-All-Reason.exe .
./Beyond-All-Reason.exe
```
