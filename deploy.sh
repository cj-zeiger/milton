pkill -f milton.py
cd /home/marodox/milton
. venv/bin/activate
pip install -U -r requirements.txt
rm nohup.out
nohup python milton.py &
