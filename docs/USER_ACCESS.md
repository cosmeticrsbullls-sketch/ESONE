# Team & Access: user/device policy

Super Admin can select Mobile Only, Computer/Web Only or Both when creating a user. The web creation form requires an explicit choice. Existing users without a policy retain Both until an administrator selects a type. Super Admin always retains Both, bypasses browser-permission setup, and retains the multiple-approved-browser exception.

Policy checks run both before successful login/device enrollment and on authenticated requests. Mismatched device classes see a dedicated access explanation; sign-out remains available. Classification uses browser client hints and User-Agent, which can be spoofed. This is not hardware attestation and does not replace the approved-device cookie.

Permissions setup requires Location and Camera only for Mobile Only/Both users currently on a mobile browser. Computer/Web Only users and desktop sessions do not request those permissions; Notifications remains optional. Super Admin skips the setup route entirely. Actual GPS/camera features still require browser consent if used explicitly.

Team & Access and Employee Details link to Employee Access. Only Super Admin can change access type or reset devices. Password reset reuses the existing audited administrator reauthentication flow.

Changing access type revokes current device approvals and disables their push subscriptions. Reset Device similarly revokes all registered browsers and stops push, requiring the employee to request approval again; it preserves password, attendance, activities and reports. Device reset requires a reason, confirmation and CSRF. Each revocation and administrative change is audited. Super Admin browsers use individual device review instead of bulk reset, preventing accidental self-lockout.

Schema: additive `user_access_policies` table created by the existing `init_db.py` startup. No destructive migration or automatic policy assignment to existing employees.

Checks: `tests.test_access_policy`, `tests.test_user_creation_csrf`, `tests.test_web_push`, `tests.test_device_camera`, `tests.test_management_passwords`, and `node tests/test_permissions.cjs`.
