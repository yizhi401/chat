#!/bin/bash

python3 main.py --login-basic=makima:makima --host=47.103.17.145:16060 --persona=psycho --photos_root=./photos/mad-mikina &

python3 main.py --login-basic=yoryor:yoryor --host=47.103.17.145:16060 --persona=writer --photos_root=./photos/AI-yor &

python3 main.py --login-basic=komikomi:komikomi --host=47.103.17.145:16060 --persona=student --photos_root=./photos/writer-komi &
