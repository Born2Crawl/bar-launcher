# bar-launcher
Simple Python launcher/updated for Beyond All Reason (BAR)

## Steps build and run the launcher

### 1. Create a virtual environment and install required libraries

```bash
python3 -m venv bar_venv
source bar_venv/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Run the script
```bash
python3 Beyond-All-Reason.py
```

### 3. Build the executable
```bash
pyinstaller -y --clean --onefile --icon icon.ico Beyond-All-Reason.py
```

### 4. Copy and run the executable (change to Beyond-All-Reason.exe for Windows)
```bash
cp ./dist/Beyond-All-Reason .
./Beyond-All-Reason
```
