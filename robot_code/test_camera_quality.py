"""Reapply camera bandwidth setting on reconnect; no camera or motors."""

from email.message import Message
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from camera_live import Relay, camera_quality_url


def main():
    url='http://192.168.8.236:81/stream'
    setting='http://192.168.8.236/control?var=quality&val=20'
    assert camera_quality_url(url,20)==setting
    assert camera_quality_url('http://[::1]:81/stream',20)=='http://[::1]/control?var=quality&val=20'
    for bad_url,quality in [(url,True),(url,-1),(url,64),('http://example.com:80/stream',20),
                            ('http://u:p@example.com:81/stream',20),(url+'?extra=1',20)]:
        try:camera_quality_url(bad_url,quality)
        except ValueError:pass
        else:raise AssertionError('Invalid camera setting accepted')
    image=np.zeros((24,32,3),dtype=np.uint8);image[:,:16,0]=255
    jpeg=BytesIO();Image.fromarray(image).save(jpeg,format='JPEG');data=jpeg.getvalue()
    packet=b'--test\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(data)).encode()+b'\r\n\r\n'+data
    relay=Relay(SimpleNamespace(camera_url=url,camera_jpeg_quality=20,max_frame_age=.5))
    calls=[]
    def open_url(address,timeout):
        calls.append(address)
        response=BytesIO() if address==setting else BytesIO(packet)
        if address==url:
            response.headers=Message()
            response.headers['Content-Type']='multipart/x-mixed-replace; boundary=test'
        return response
    original=relay.record_frame
    def record(jpeg):
        frame=original(jpeg)
        if relay.sequence==2:relay.stopping.set()
        return frame
    relay.record_frame=record
    with patch('camera_live.build_opener',return_value=SimpleNamespace(open=open_url)):
        relay.capture()
    assert calls==[setting,url,setting,url]
    assert relay.sequence==2 and relay.generation>=1
    print('PASS: bounded camera setting, IPv6 origin, JPEG decoding and quality reapplied after reconnect')


if __name__=='__main__':main()
