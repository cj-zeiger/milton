pkill -f milton.py
cd /home/asc/milton
. venv/bin/activate
pip -r requirements.txt
nohup python milton.py &
