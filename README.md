# https://radio.charles.systems/

This is a small Flask app I put together to track what songs I listen to on Spotify. 

To run your own instance, join the [Spotify developer program](https://developer.spotify.com/) and create a new project. Make sure to add your desired URL to the "Redirect URIs" field.
Create a file called `.env` in the root directory that contains the following:
```
SPOTIFY_CLIENT_ID=<your client id>
SPOTIFY_REDIRECT_URI=<etc.>
SPOTIFY_CLIENT_SECRET=<etc.>
SPOTIFY_ACCESS_TOKEN=<etc.>
```

Create `/etc/systemd/system/radio.service` that looks like
```
[Unit]
Description="Gunicorn instance to serve radio.charles.systems"
After=network.target

[Service]
User=root
ExecStart="/root/radio.charles.systems/startup.sh"

[Install]
WantedBy=multi-user.target
```

```
sudo systemctl start radio
sudo systemctl enable radio
```
