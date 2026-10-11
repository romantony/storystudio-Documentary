# Connecting to the doc-gen instance and re-authenticating Storyblocks

This is the guide for a person who needs to get onto the doc-gen EC2 instance: to sign the Storyblocks MCP in again, to look at a problem, or to edit something from the desktop. The instance has no open ports. Everything goes through AWS Systems Manager (SSM), so all you need is AWS credentials.

| Item | Value |
|---|---|
| Instance | `i-0a6c5182dd9377129`, region `us-east-1` |
| Desktop | XFCE in the browser (noVNC), port 6080 on the instance, reached through an SSM tunnel |
| Desktop password | Parameter Store, `/docgen/VNC_PASSWORD` |
| Container | `docgen-docgen-1`, started automatically at boot |
| Storyblocks sign-in is stored in | `/data/claude` in the container (`/data/docgen/data/claude` on the instance disk) |

## 1. When Storyblocks needs signing in again

Any of these means the sign-in is missing or has expired:

- `GET /v1/health` shows `"storyblocks_mcp": "needs_login"` (or `not_configured`) and `"ready": false`.
- `POST /v1/documentaries` answers 503 with `"code": "not_ready"`.
- A job fails with error code `storyblocks_auth`.

The sign-in survives stopping and starting the instance and survives image updates; this was tested on 2026-10-11. How long Storyblocks keeps a sign-in valid is not known yet, so expect to repeat section 4 from time to time.

## 2. One-time setup on your computer

1. **AWS CLI** with credentials that can use SSM and EC2 on this account (`aws sts get-caller-identity` should work).
2. **Session Manager plugin**, which the tunnel needs. On Ubuntu or Debian:
   ```
   curl -o /tmp/session-manager-plugin.deb https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb
   sudo dpkg -i /tmp/session-manager-plugin.deb
   ```
   For macOS and Windows, see "Install the Session Manager plugin" in the AWS documentation.

## 3. Open the desktop

1. **Start the instance and keep it awake.** Without the tag, the instance stops itself after 20 minutes with no job and no API call, even while you are using the desktop.
   ```
   aws ec2 start-instances --instance-ids i-0a6c5182dd9377129
   aws ec2 create-tags --resources i-0a6c5182dd9377129 --tags Key=keep-awake,Value=1
   ```
   Wait about a minute.
2. **Open the tunnel.** Leave this running in its own terminal.
   ```
   aws ssm start-session --target i-0a6c5182dd9377129 --document-name AWS-StartPortForwardingSession --parameters portNumber=6080,localPortNumber=6080
   ```
3. **Get the desktop password.**
   ```
   aws ssm get-parameter --name /docgen/VNC_PASSWORD --with-decryption --query Parameter.Value --output text
   ```
4. **Open `http://localhost:6080/vnc.html`** in your browser, click Connect and enter the password.

Copy and paste between your computer and the desktop goes through the clipboard panel in the noVNC side bar (the tab on the left edge of the screen).

## 4. Re-authenticate the Storyblocks MCP

On the remote desktop, open a terminal (Applications, Terminal Emulator).

1. Check the current state:
   ```
   claude mcp list
   ```
   - `storyblocks ... Connected`: nothing to do.
   - `storyblocks ... Needs authentication` or similar: continue with step 2.
   - No `storyblocks` line at all: add the server first, then continue.
     ```
     claude mcp add --transport http storyblocks https://mcp.storyblocks.com/mcp --scope user
     ```
2. Start Claude Code and open the MCP menu:
   ```
   claude
   ```
   Type `/mcp`, select **storyblocks**, then **Authenticate**. If it claims to be connected but jobs still fail, choose **Clear authentication** first and then **Authenticate**.
3. Firefox opens on the remote desktop. Sign in to Storyblocks and approve access. If Firefox does not open, copy the URL Claude Code prints into Firefox **on the remote desktop**. It does not work in the browser on your own computer, because the sign-in finishes by redirecting to an address on the instance.
4. Back in the terminal, `/mcp` should show storyblocks as connected. Leave with `/exit`.

## 5. Confirm it worked

In the same terminal on the remote desktop:

```
claude mcp list
curl -s -H "Authorization: Bearer $DOCGEN_API_TOKEN" -H "X-Origin-Verify: $DOCGEN_ORIGIN_SECRET" http://127.0.0.1:8080/v1/health
```

The second command should show `"storyblocks_mcp": "connected"` and `"ready": true`. The health check caches the Storyblocks result for 60 seconds, so wait a minute if it still shows the old state.

The public URL, `https://doc-gen.ai-storystudio.com`, answers only the orchestrator's address. From anywhere else it returns 403, so check from the instance as above or from the orchestrator host.

## 6. Finish

1. Close the tunnel with Ctrl+C.
2. Remove the tag, otherwise the instance runs (and bills) until someone stops it:
   ```
   aws ec2 delete-tags --resources i-0a6c5182dd9377129 --tags Key=keep-awake
   ```
3. Either stop the instance now, or leave it: it stops itself after 20 idle minutes.
   ```
   aws ec2 stop-instances --instance-ids i-0a6c5182dd9377129
   ```

## 7. A shell without the desktop

For looking at logs or running a command, a shell is quicker than the desktop.

```
aws ssm start-session --target i-0a6c5182dd9377129
```

Useful commands once in:

| Purpose | Command |
|---|---|
| Is the container up | `sudo docker ps` |
| Container start-up log | `sudo docker logs --tail 50 docgen-docgen-1` |
| API log | `sudo tail -50 /data/docgen/data/runs/api.log` |
| A shell inside the container | `sudo docker exec -it docgen-docgen-1 bash` |
| Job folders | `ls /data/docgen/data/runs` |
| What one job did | `sudo tail /data/docgen/data/runs/<job_id>/runner.jsonl` |
| Restart the service (pulls the newest image) | `sudo systemctl restart docgen.service` |
| Free disk space | `df -h /` |

Do not restart the service while a job is running: the job is lost and reported as failed.

## 8. Other changes you might need

- **A new image.** Start a build (`aws codebuild start-build --project-name docgen-image`). The instance pulls `latest` at every boot, or immediately with `sudo systemctl restart docgen.service`.
- **A changed API key or secret.** Update the parameter under `/docgen/` in Parameter Store, then restart the service or the instance; the values are read at start. If you change `/docgen/DOCGEN_ORIGIN_SECRET`, also change the `X-Origin-Verify` origin header on CloudFront distribution `E3RSXC7W2L5H0P`, or every call returns 403.
- **A new desktop password.** Change `/docgen/VNC_PASSWORD` and restart the service. Only the first 8 characters are used.
- **The orchestrator's address changed.** Edit the address list in the CloudFront function `docgen-allow-orchestrator` and publish it.
- **Editing the scripts from the desktop.** VS Code is installed (`code /app`). Changes under `/app` are lost when the container restarts, because `/app` comes from the image. Make lasting changes in the git repository and rebuild.

## 9. If something does not work

| Symptom | Likely cause and fix |
|---|---|
| `start-session` fails with "SessionManagerPlugin is not found" | Install the plugin (section 2). |
| `start-session` fails with "TargetNotConnected" | The instance is stopped or still booting. Start it and wait a minute. |
| `localhost:6080` does not load | The tunnel is not running, or the container is not up. Check with `sudo docker ps` in a shell (section 7). |
| The desktop disappears while you work | The instance stopped itself. Set the `keep-awake` tag (section 3) and start it again. |
| The password is rejected | Read it again from Parameter Store; it may have been changed. |
| The desktop is a blank grey screen | Restart the service (section 7), then reconnect. |
| Firefox shows a redirect error after signing in | The sign-in was started in a browser on your own computer. Start it again from Firefox on the remote desktop. |
| Health still says `needs_login` after signing in | Wait 60 seconds for the cached check, then call health again. |
