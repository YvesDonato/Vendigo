import os
import subprocess

root = '/ssd1/userdata/donatoy/openjev-follow-20260919'
subprocess.run(['systemd-run','--user','--collect','--unit=openjev-camera',
    '--description=ESP32 YOLO26s tracking and rule-based following',
    '--property=WorkingDirectory=/home/yvesd/codingspace/testML/iPlanner',
    '--property=Restart=on-failure','--property=RestartSec=2','--property=TimeoutStopSec=15',
    '--setenv=SSH_AUTH_SOCK='+os.environ.get('SSH_AUTH_SOCK','/run/user/1000/gcr/ssh'),
    '/tmp/iplanner-openjev-check/bin/python','-u','camera_live.py',
    '--ssh-host','H100','--remote-dir',root,
    '--camera-jpeg-quality','20',
    '--camera-calibration',root+'/robot-trial/camera-code/deberta-camera-calibration.json',
    '--follow-person','--follow-gap','0.25','--follow-distance-scale','1.0',
    '--robot-url','http://192.168.8.100',
    '--robot-token-file','/home/yvesd/Codebases/auto-dash/robot_code/control.token',
    '--stop-distance-cm','25','--drive-speed','255','--turn-speed','255',
    '--search-rotation-seconds','3.184'],check=True)
print('Started YOLO26s + BoT-SORT with rule-based following. Steering disabled until Start is pressed.')
