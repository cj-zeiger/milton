pkill -f milton.py
cd /home/asc/milton
. venv/bin/activate
pip install -U -r requirements.txt
nohup python milton.py &
