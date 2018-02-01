(
  echo aiohttp
  echo websockets
) > %cd%\r.txt
python -m pip install --upgrade pip
pip install -r %cd%\r.txt
