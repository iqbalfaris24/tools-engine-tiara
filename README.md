# tools-engine-tiara

## Install Requirements
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

```

## Dev
```
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 9090 --reload
deactivate
pip freeze > requirements.txt
```

##Staging/Production
```
pm2 start /home/iqbalfaris/python/tools-engine-tiara/venv/bin/python --name "tools-tiara" --interpreter none -- -m uvicorn main:app --host 0.0.0.0 --port 8082
```