#!/bin/bash
# Start XFCE once the VNC X server is accepting connections. dbus-run-session gives the session its own bus;
# without it xfce4-session starts but never launches the window manager or panel.
for i in $(seq 1 50); do [ -S /tmp/.X11-unix/X1 ] && break; sleep 0.2; done
exec dbus-run-session -- xfce4-session
