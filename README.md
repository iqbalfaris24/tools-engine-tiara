# tools-engine-tiara

## Install Requirements
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

```

## Dev
```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
pip freeze > requirements.txt
deactivate
```

##Staging/Production

```bash
pm2 start /home/iqbalfaris/Documents/python/tools-engine-tiara/venv/bin/python \
--name "tools-tiara" \
--interpreter none \
-- -m uvicorn main:app --host 0.0.0.0 --port 8082 --reload

pm2 start /media/iqbalfaris/Data/Programming/Python/tools-engine-tiara/venv/bin/python \
--name "tools-tiara" \
--cwd /media/iqbalfaris/Data/Programming/Python/tools-engine-tiara \
-- -m uvicorn main:app --host 0.0.0.0 --port 9091
```