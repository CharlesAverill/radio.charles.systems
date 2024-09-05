#!/usr/bin/bash
cd /root/radio.charles.systems
source venv/bin/activate
gunicorn app:app --bind 0.0.0.0:80
