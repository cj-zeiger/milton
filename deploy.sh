pkill -f milton.py
cd /home/marodox/milton
. venv/bin/activate
pip install -U -r requirements.txt
nohup python milton.py &
