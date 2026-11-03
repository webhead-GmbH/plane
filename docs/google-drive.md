# Google Drive

This page is for the workspace admin who connects Plane to the company's Google Drive, and for anybody who wonders where a file they attached to a work item has gone. It explains what the connection does, how to set it up once in Google Cloud, how each project gets its folder, and where the files of a work item end up.

## Contents

- [What it does](#what-it-does)
- [Before you start: a Google Cloud client](#before-you-start-a-google-cloud-client)
- [Connecting](#connecting)
- [The projects folder](#the-projects-folder)
- [Giving each project its folder](#giving-each-project-its-folder)
- [New projects](#new-projects)
- [Files on a work item](#files-on-a-work-item)
- [Removing a file](#removing-a-file)
- [Who may do what](#who-may-do-what)
- [Disconnecting](#disconnecting)
- [Messages you may see](#messages-you-may-see)

## What it does

Once a workspace is connected and a project has a Drive folder, every file put on one of that project's work items goes to Google Drive instead of the Plane server:

- files attached with **Attach** or dropped on the attachments list,
- images and files pasted or dropped into the description,
- images and files pasted or dropped into a comment.

There is no limit on the size, the type or the number of files. Each work item gets its own folder, `Tasks/<work item ID>`, inside its project's folder, for example `Fisch Gruber/Tasks/FISCH-12`. Images are shown in Plane as before; Plane asks Google for a resized copy and never keeps one itself.

The bytes go from the browser straight to Google. Where a browser or a network will not let them, they pass through the Plane server one small piece at a time, and are not stored there either.

Projects without a Drive folder keep working exactly as before, with Plane's own storage and limits.

## Before you start: a Google Cloud client

Plane signs in to Google with a client that belongs to your company, so the files stay between you and Google. Making one takes a few minutes in the [Google Cloud Console](https://console.cloud.google.com/):

1. Create a project, or choose an existing one, and enable the **Google Drive API** (APIs & Services → Library).
2. Set up the **OAuth consent screen** (APIs & Services → OAuth consent screen). With a Google Workspace account, choose **Internal**: only people in your company can then sign in, and Google does not review the app.
   - If you choose **External** instead and leave the app in **Testing**, Google expires the sign-in after seven days and Plane loses access. Publish the app, or use Internal.
3. Create an **OAuth client ID** of the type **Web application** (APIs & Services → Credentials).
4. Under **Authorized redirect URIs**, add the address shown on Plane's Google Drive settings page. It is your Plane address followed by `/api/gdrive/oauth/callback/`, for example `https://plane.example.com/api/gdrive/oauth/callback/`. It must match exactly.
5. Copy the **client ID** and the **client secret**.

Plane asks for full Drive access (`https://www.googleapis.com/auth/drive`). The narrower scope only reaches files Plane made itself, and your project folders already exist.

## Connecting

Open **Workspace settings → Integrations → Google Drive**, paste the client ID and client secret, and press **Connect with Google**. Sign in with the Google account that should own the uploaded files — ideally one that can reach every project folder, such as a shared office account — and allow access.

Google sends you back to the settings page, which then says which account is connected. Every file Plane puts in Drive is created as that account, so it counts against your company's Drive storage, not the Plane server's.

The client secret and Google's token are stored encrypted, and neither is ever shown again. To use another Google account, press **Connect again**. A new client ID disconnects the current account; connect again afterwards.

## The projects folder

Choose the folder your project folders are in, for example `projects / webhead`. Only its folders are offered when you give a project its folder, so the list does not show the whole of Drive.

Press **Choose folder** and walk down to it: the top level shows My Drive, Shared with me and each shared drive. Or open the folder in Google Drive, copy the address from the browser, and paste it under **Or paste a link to the folder**.

## Giving each project its folder

The **Project folders** list shows every project with the folder it keeps its files in.

- For a project without one, the folders whose names look like the project's come first in the list, with how close the match is. Names are compared without case, accents, spaces or punctuation.
- A folder is a **clear match** when it carries the project's own name, give or take spacing, punctuation, a company form such as GmbH or e.U., or one letter: for the project "Fisch Gruber", `fisch-gruber`, `Fisch Gruber GmbH` and `Fish Gruber` are clear matches. `Gruber`, `Fischer Gruber` or `Fisch Gruber 2024` are only suggested, because they may be another client's folder. Two clear matches for one project are not chosen between either.
- **Use "…"** links a project to its clear match in one click, and **Link N clear matches** at the top links all such projects at once. Everything else is left for you to choose.
- The **⋯** menu next to the list can create a folder named after the project, or choose a folder anywhere in Drive, even outside the projects folder.
- A linked project shows its folder (it opens in Google Drive) and how it was linked: chosen, matched by name, or created by Plane. Its **⋯** menu changes or unlinks the folder. Unlinking leaves the folder and its files in Drive.

## New projects

With **Give new projects a folder** switched on, a new project is linked as soon as it is created: to its clear match in the projects folder, or, if there is none, to a new folder named after it there. This happens in the background and takes a few seconds. A project whose name has two clear matches gets a new folder of its own; link it to the right one in the settings if that is what you meant.

## Files on a work item

On a work item of a linked project, the attachments section says **Stored in Google Drive** and has an **Open folder** link to the work item's folder.

- **Attach** takes several files at once. Each one shows its progress while it uploads.
- Click an image to see it larger; **Open in Google Drive** opens any file in Drive.
- An image pasted or dropped into the description or a comment appears as an image, as before. Any other file appears as a link with the file's name where you dropped it, and opens in Drive.

Files that were attached before the project was linked stay in Plane's own storage and are listed as before.

## Removing a file

Removing an attachment in Plane moves the file to Google Drive's bin, where it can be restored for 30 days. An image or file deleted from the description or a comment stays in the work item's folder in Drive; remove it there if it is no longer wanted.

## Who may do what

- Connecting, choosing the projects folder and linking projects: workspace admins.
- Uploading: anybody on the project.
- Removing an attachment: the person who uploaded it, or a project admin.
- Seeing an image or opening a file through Plane: anybody on the file's project, and workspace admins. Opening a file in Google Drive itself depends on who the folder is shared with there.

## Disconnecting

**Disconnect** stops new files from going to Drive: they are stored in Plane again. Files already in Drive stay there, and the project folder links are kept, so connecting again picks up where it was.

## Messages you may see

| Message                                                | What it means                                                                                                    |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| Plane no longer has access to Google Drive.            | The connected account's access was withdrawn or expired. A workspace admin presses **Connect again**.            |
| This project has no Google Drive folder yet.           | Give the project its folder in the settings.                                                                     |
| The connected Google account can't access this folder. | Share the folder with the connected account in Google Drive, or choose another folder.                           |
| The Google Drive storage is full.                      | Free up space in Drive or buy more; nothing can be uploaded until then.                                          |
| Google didn't accept the sign-in.                      | Check the client ID, the client secret and the redirect URI in Google Cloud, then connect again.                 |
| Google didn't grant lasting access.                    | Remove Plane from the Google account's third-party access (myaccount.google.com → Security), then connect again. |
