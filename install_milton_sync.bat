(
  echo aiohttp==0.21.6
  echo websockets==3.1
) > %cd%\r.txt
python -m pip install --upgrade pip
pip install -r %cd%\r.txt