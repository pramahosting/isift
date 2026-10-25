# isiftmail: email for anyone (name@isiftmail.com), or on your own domain (you@your-company.com)

isiftmail gives **anyone with an iSift sign-in** an address of their own inside **Commbox > Mail**, free on your isiftmail domain, or on **their own domain** hosted here, much like Microsoft 365 email at GoDaddy. It includes inbox, folders, writing, replying, drafts, deleting, a signature, an auto-reply and spam filtering. It is optional. Until you set it up (step 4) nobody sees it, and the rest of Commbox works exactly as before.

## How it fits together

```
 iSift (this app)  --IMAP 993 / SMTP 587 / ManageSieve 4190-->  Stalwart mail server (your VPS)  --outbound relay-->  the internet
        |                                                              ^
        +---------- management address (HTTPS): create / close mailbox |
 the internet --port 25 (incoming mail)---------------------------------+
```

* **Stalwart** stores the mail, receives mail from the internet and filters spam.
* **iSift** shows the mailbox (it reads and sends over IMAP and SMTP, like any other Commbox account) and manages mailboxes through Stalwart's management address.
* **The outbound relay** (a sending service such as Amazon SES, Mailgun or Postmark) delivers outgoing mail, so Gmail, Hotmail and Yahoo accept it from a brand-new server. Stalwart is set to pass outgoing mail to the relay; iSift never holds the relay's login. You can remove the relay later if your own server earns a good reputation.

## 1. The server (one small VPS)

* A VPS with 2 GB RAM / 20 GB disk is enough for a pilot; 4 GB for a few hundred people. Choose a host that **allows outbound port 25** (confirm with their support before you pay; AWS, Google Cloud and some budget hosts block it) and gives you **reverse DNS (PTR)** control.
* Install **Stalwart Mail Server version 0.15.x** (Docker or the installer from stalw.art). iSift's management calls use the REST `/api/principal` interface of 0.15 and earlier. Newer Stalwart versions moved account management to JMAP; if you install a newer one, only `backend/app/integrations/isiftmail.py` needs changing.
* In Stalwart: add your domain (for example `isiftmail.com`), turn on automatic TLS certificates (ACME) for `mail.isiftmail.com`, create an administrator account for iSift, and keep the spam filter on.
* Open ports: 25 (incoming mail), 587 and 465 (sending), 993 (reading), 443 (management and web admin), 4190 (ManageSieve, for auto-reply). Port 4190 only needs to be reachable from the machine that runs iSift: firewall it to that address.

## 2. DNS (at your domain registrar)

| Record | Name | Value |
|---|---|---|
| A | `mail.isiftmail.com` | the VPS address |
| MX | `isiftmail.com` | `mail.isiftmail.com` (priority 10) |
| TXT (SPF) | `isiftmail.com` | `v=spf1 mx include:<your relay's SPF> -all` (the relay tells you the exact include) |
| TXT (DKIM) | `<selector>._domainkey.isiftmail.com` | the key Stalwart shows for the domain (and the relay's own DKIM records, if it asks for them) |
| TXT (DMARC) | `_dmarc.isiftmail.com` | `v=DMARC1; p=quarantine; rua=mailto:postmaster@isiftmail.com` |
| PTR (reverse DNS) | the VPS address | `mail.isiftmail.com` (set at the VPS host) |

Check the result at mail-tester.com before you invite anyone.

## 3. The outbound relay

1. Make an account with the relay service, verify `isiftmail.com` there, and get its SMTP host, port and login.
2. In Stalwart, add that service as the **remote relay** and send every non-local recipient through it (Stalwart's "queue / outbound next-hop" and "remote relay" settings; the names differ slightly between versions, so follow the relay section of the Stalwart documentation for your version).
3. Send a test message from a mailbox to a Gmail address and confirm it arrives in the inbox, not Spam.

Cost guide: one VPS about A$8 to A$25 a month, the domain about A$20 a year, a relay about A$1 per 10,000 messages.

## 4. Tell iSift (Admin Console)

**Admin Console > API and Settings > Email and calendar > isiftmail (our own email service)**:

| Setting | Example |
|---|---|
| Address domain | `isiftmail.com` |
| Mail server management address | `https://mail.isiftmail.com` |
| Administrator name / password or token | the Stalwart administrator you made (leave the name empty to use a token) |
| Mailbox (IMAP) server / port | `mail.isiftmail.com` / 993 |
| Sending (SMTP) server / port | `mail.isiftmail.com` / 587 |
| Auto-reply (ManageSieve) port | 4190 |
| Mailbox size for each person | 2048 MB |
| Mail (MX) name for people's own domains | `mail.isiftmail.com` (empty = the IMAP server) |
| SPF record shown for people's own domains | `v=spf1 mx include:<your relay's SPF include> ~all` |

The same values can come from the environment: `ISIFTMAIL_DOMAIN`, `ISIFTMAIL_API_URL`, `ISIFTMAIL_API_USER`, `ISIFTMAIL_API_PASSWORD`, `ISIFTMAIL_IMAP_HOST`, `ISIFTMAIL_IMAP_PORT`, `ISIFTMAIL_SMTP_HOST`, `ISIFTMAIL_SMTP_PORT`, `ISIFTMAIL_SIEVE_PORT`, `ISIFTMAIL_QUOTA_MB`, `ISIFTMAIL_MX_HOST`, `ISIFTMAIL_SPF`.

The on/off switch is **Admin Console > Customers > Modules > Commbox: isiftmail**. It can also be left out of a plan under **Customers > Plans**. Turned off, the offer disappears and the isiftmail routes refuse requests; people who already have an address keep their mail on the server.

## Who can have an address

Anyone who can use Commbox. (Commbox's own plan rule still applies: the Basic plan has no Commbox unless an administrator allows it. To open isiftmail to Basic customers as well, allow Commbox for that plan under Customers > Plans.) A person has **one free address** on your isiftmail domain; the administrator can make more. Closed addresses are held back for 180 days so nobody can take over mail meant for the previous owner.

## Own domains (pramod@prama-ai.com)

In **Commbox > Mail > Use my own domain** a person:

1. **Adds the domain** (for example `prama-ai.com`). iSift shows the DNS records to add where the domain is managed (GoDaddy, Cloudflare, and so on): an **ownership TXT** record, the **MX** record, **SPF**, **DKIM** (shown once the domain is verified) and **DMARC**.
2. **Presses Check my DNS.** iSift looks the records up on the internet. When the ownership record is found the domain is **verified**: only then is it set up on the mail server and can mailboxes be made on it. Nobody can hold a domain they do not control, and if two people add the same domain the one who proves it first keeps it. Mail only arrives once the MX record is in place, and the page says so.
3. **Makes mailboxes**: their own (`pramod@prama-ai.com`) and, like the Microsoft 365 admin centre, **for team members**: give the member's iSift sign-in email and the mailbox appears in their Mail (right away if they have an account, or the first time they sign in). The domain owner can **reset the password** and **close** any mailbox on their domain, see which are waiting, and remove the domain once no mailbox is left on it. Up to 3 domains per person and 50 mailboxes per domain. The reserved-names list applies only to the free isiftmail domain: `info@` and `postmaster@` are fine on your own domain.

On the mail server each mailbox on a person's own domain has the login name `name.domain-with-dashes` (for example `pramod.prama-ai-com`), so two companies can both have `info@`. People never need it: iSift stores the login and password. They are shown (once) only for using the mailbox in Outlook or a phone.

The mail server calls used for domains are the Stalwart 0.15 REST ones: `POST /api/principal` with `"type":"domain"`, `POST /api/dkim`, and `GET /api/dns/records/<domain>` (which supplies the DKIM record). They are in `backend/app/integrations/isiftmail.py`. If your Stalwart version words any of them differently, the page still works: the DKIM record is simply not shown until the mail server provides it, and you can add the domain's DKIM record by hand from Stalwart's own admin screen.

## Outlook, Thunderbird and phone auto-setup

For a person's own domain iSift also shows three more records (recommended, and checked by **Check my DNS**): `autodiscover.<domain>` and `autoconfig.<domain>` (both CNAMEs to the **Auto-setup name** in Admin Console) and an `_autodiscover._tcp.<domain>` SRV record. With them, Outlook, Thunderbird and phones set themselves up from just the address and password.

iSift answers the requests itself, with no sign-in: `/autodiscover/autodiscover.xml` (Outlook) and `/mail/config-v1.1.xml` (Thunderbird, phones), only for your isiftmail domain and for verified own domains. Two things you must do on the server side:

* The **Auto-setup name** (setting `isiftmail_autoconfig_host`, default is the mail name) must be a name with a valid HTTPS certificate that reaches those two addresses, for example your reverse proxy forwarding them to the iSift app.
* Outlook connects to `https://autodiscover.<their-domain>/...`, and a CNAME cannot give that name a certificate for the customer's domain. Outlook therefore follows the SRV record and asks the person once to **allow the redirect** to your Auto-setup name. That prompt is normal. Without it, people still can set up by hand from the server details iSift shows.

## What people get

Inbox, Sent, Drafts, Junk and Deleted folders; reading, replying, forwarding, deleting and moving; **Save draft** and **Edit draft** (isiftmail addresses); a **signature** added to new messages; an **auto-reply** with optional start and end dates (a Sieve "vacation" rule on the server, once a day per sender); a **new password** for using the mailbox in Outlook or a phone app; and **Close this mailbox**. Each address has its own signature and auto-reply. Spam filtering is Stalwart's built-in filter; "Junk" in Commbox moves a message to the Junk folder.

## Spam control (built in)

Open sign-up invites spam senders, so iSift limits and watches every isiftmail mailbox. The numbers are in Admin Console under the isiftmail settings:

* **Sending limits** per mailbox: messages per hour (30), per day (200; a mailbox under a day old gets a quarter of that) and people in one message (50). Over a limit, iSift refuses the message and says when to try again.
* **New addresses**: a person can open only one free address, and one network address can open only a few a day (default 3, times 3 signed-in people).
* **Automatic suspension**: after 3 spam complaints or 20 hard bounces a mailbox is suspended. Its password on the mail server is replaced (so nobody, including Outlook or a phone, can send or read) and iSift refuses to send from it. An administrator restores it in **Customers > Mailboxes**, which also lists every mailbox with messages sent in 24 hours, complaints and bounces, and has Suspend and Restore buttons. Restoring puts the original password back and clears the counters. Every suspension is in the audit log.
* **Complaint and bounce notices from your outbound relay.** Set **Secret for relay complaint and bounce notices** in Admin Console, then give your relay this address as its webhook (for example an Amazon SES notification or any relay webhook):
  `https://<your iSift address>/api/v1/isiftmail/hooks/relay?secret=<the secret>`
  iSift reads a list `{"events":[{"type":"complaint","from":"name@isiftmail.com"}]}` or one event, and the usual relay shapes (`notificationType`, `mail.source`, `bounceType`). Temporary bounces are ignored. Without the secret the address refuses everything.
* **Public abuse report.** `POST /api/v1/isiftmail/report` with `{"address":"name@isiftmail.com"}` needs no sign-in (5 reports an hour from one network address); every report counts as a complaint. Link it from an "abuse@" page or autoresponse.
* Also set limits **on the mail server** (Stalwart: outbound rate limits, and keep the relay's own sending cap on) so a hijacked login cannot go around iSift by connecting to the mail server directly. These limits apply to mail sent through iSift's Mail screens.

## Before you open it to the public

* Test with 3 or 4 people first, including sending to and from Gmail, Outlook.com and Yahoo.
* Limit abuse: switch on the relay notices above, check Customers > Mailboxes weekly, and set sending limits on the mail server too.
* Back up the Stalwart data folder daily and test a restore.
* Add the mail terms to your Terms of Use and Privacy Policy (you store people's messages), and comply with the Spam Act 2003.
* What has not been tested here: the connection to a real Stalwart server or real DNS. The management calls (including the domain ones), ManageSieve, IMAP draft saving and the DNS lookups were tested against stand-ins, so run the checks above on your server, with one real domain, before announcing it.
* Letting anyone open an address makes your domain a target for spam senders. The built-in limits and suspension (above) reduce it but do not replace watching your relay's reports.
