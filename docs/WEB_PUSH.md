# First-login browser setup and Web Push

Approved logins and the Device approval Continue link open `/permissions`. The page checks Location, Camera and Notifications without prompting automatically. Buttons request permissions on a user gesture. Camera verification closes all media tracks immediately; the GPS check does not write attendance or coordinates. Location and Camera gate the page's Home button; Notifications can be skipped. Office reviewers retain a Command Center link so unavailable desktop hardware cannot block device approvals.

Known grants skip repeated setup on subsequent logins. Where browser permission queries are unavailable, a per-user/per-device local marker is shown as previously checked, not as a verified current grant. Field forms still enforce real GPS and camera requirements. Notifications has a management link to `/permissions?manage=1` so users can test or turn off push without automatic redirection. iPhone/iPad push requires a supported OS and a Home Screen install.

The app uses standard VAPID Web Push, not a paid provider. A single signing key is generated server-side in `web_push_keys`; only its public key reaches the browser. Preserve the private key/database across deployments and keep it out of logs and public exports. The root-scoped worker is served with `Service-Worker-Allowed: /`; it does not cache application pages.

Subscriptions bind to approved device IDs, account IDs and the current password fingerprint. Endpoints are restricted to supported browser push services and key shapes are validated. Subscribe, test and unsubscribe require CSRF. Only one active endpoint per device is retained. Account switching, logout, device revocation and password changes prevent further sends. A test is limited to once per 30 seconds.

The background dispatcher polls the existing role-scoped notification inbox every minute. It includes activity/assignment changes, existing due reminders, and demo request decisions. Records older than subscription/read time are not backfilled. Delivery keys suppress repeats; transient failures back off and retry up to five attempts; HTTP 404/410 disables expired subscriptions. Push payloads use generic text and authenticated internal destinations rather than exposing salon details on the lock screen. In-app updates remain the source of truth.

Operational requirement: the dispatcher runs in the web service process. An idle/sleeping free hosting instance cannot deliver punctual scheduled reminders until it wakes. Always-on hosting or an independently scheduled dispatcher is needed for dependable timing; no hosting plan change is part of this implementation.

Validation:

- `PYTHONWARNINGS=ignore PYTHONPATH=.:tests python -m unittest tests.test_web_push tests.test_device_camera tests.test_enhancements tests.test_workflows tests.test_team_orders -q`
- `node tests/test_permissions.cjs`
- Real device acceptance after deployment: first-login Allow prompts, camera indicator turns off after check, approved-device subscription, test notification with ESONE backgrounded, tap destination, optional skip/off, iPhone Home Screen install and actual delivery.

No deployment or real-device permission grant is performed by adding this feature branch.
