# TeamArlington
Software Design class 2025 project 

**Team Members:**  
Rindy Tuy, Oluchi Nwabuoku, Cong Duy Vuong Dao, Rasinie Karen Seunsom

---

## Project Overview

We're building an **O365 Role-Based Access Control (RBAC) system** - a web application that lets administrators manage user access and permissions in an organization using Office 365 authentication.

### Key Features
1. **Authentication** - Login with Office 365 accounts
2. **User Management** - Add, edit, view, and remove users
3. **Roles & Permissions** - Control access levels (Admin vs Basic User)
4. **User Deactivation** - Temporarily disable accounts

> For detailed feature documentation, see [userManagement.md](userManagement.md)

---

## Tech Stack

- **Flask** - Python web framework
- **MSAL** - Microsoft Authentication Library
- **SQLite** - Database for user storage
- **HTML/CSS** - Frontend templates and styling

---

## Project Structure

```
/TeamArlington
  /app
    __init__.py              # Main app setup
    /auth                    # Everything related to login/logout
      routes.py              # Login, logout, callback URLs
    /users                   # Everything related to user management
      routes.py              # List, add, edit, delete users
    /ui
      /templates             # HTML pages
        base.html            # Layout used by all pages
        home.html            # Landing page
        auth_login.html      # Login page
        users_list.html      # User management page
      /css
        style.css            # Custom styling
  run.py                     # Starts the application
  requirements.txt           # Python packages needed
```

## How Data Flows

1. **User visits website** → Flask receives request
2. **Flask checks route** → Finds matching function
3. **Function runs** → Gets data from database if needed
4. **Renders template** → Fills in HTML with data
5. **Sends back to user** → Browser displays page

## Key Concepts

### Blueprints
Think of blueprints as mini-apps within the main app. We have:
- `auth_bp`: Handles login/logout
- `users_bp`: Handles user management

### Routes
Routes are URLs that do things:
- `/` → Home page
- `/auth/login` → Login page
- `/users` → User list page

### Sessions
After you log in, Flask remembers you so you don't have to log in on every page.

## How to Setup and Run

1. **Configure environment variables:**
   - Edit `.env` and add your Microsoft Azure credentials:
     ```
     CLIENT_ID=your-client-id-here
     CLIENT_SECRET=your-client-secret-here
     TENANT_ID=your-tenant-id-here
     FLASK_SECRET_KEY=your-flask-secret-key
     ```
   - Get these credentials from [Azure Portal](https://portal.azure.com) by registering an app

2. **Install the required packages:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python3 run.py
   ```

4. **Open your web browser and go to:**
   ```
   http://localhost:5000
   ```

---

## Documentation

- **[userManagement.md](userManagement.md)** - Detailed feature implementation guide
- **[graphs/contributors.md](graphs/contributors.md)** - Team member contributions

---

## PDF Generation (LaTeX)

- The utility `app/utils/pdf_generator.py` generates PDFs using LaTeX (`pdflatex`) via a Makefile in the `latex_templates/` directory.
- System requirement: you must have a LaTeX distribution installed that provides `pdflatex` (e.g., TeX Live or MiKTeX).
  - macOS: `brew install mactex-no-gui` (or install MacTeX from https://tug.org/mactex/)
  - Linux: install TeX Live (`texlive-full` or the packages providing `pdflatex`).
  - Windows: install MiKTeX.
- The folder `latex_templates/` is created at runtime if missing.
- On first PDF generation, a `Makefile` is written automatically with a pattern rule to compile `.tex` to `.pdf` using `pdflatex`.


## Note for TAs
This project uses Microsoft 365 OAuth for authentication.
Since you may not have access to our registered Azure credentials, the login feature may not fully work.
However, the rest of the application and its routes can still be accessed and tested through Docker.

How to run in Docker:

docker build -t teamarlington-app .
docker run -p 5001:5001 teamarlington-app

