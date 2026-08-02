# Maa Tara HP Gas - Deployment Guide (PythonAnywhere Free)

## Architecture

-   Hosting: PythonAnywhere (Free)
-   Database: SQLite
-   Source Control: GitHub
-   Framework: Django

------------------------------------------------------------------------

# One-time Setup (Already Done)

-   Created PythonAnywhere account
-   Cloned GitHub repository
-   Created virtual environment
-   Installed requirements
-   Configured WSGI
-   Configured Static Files
-   Ran collectstatic
-   Reloaded the web app

------------------------------------------------------------------------

# Daily Deployment Workflow

## Step 1 - Local VS Code

``` bash
git status
git add .
git commit -m "Describe your changes"
git push origin main
```

## Step 2 - PythonAnywhere Bash Console

``` bash
cd ~/Maa-Tara-HP-Gas
source .venv/bin/activate
git pull origin main
```

## Step 3 - If requirements.txt changed

``` bash
pip install -r requirements.txt
```

## Step 4 - If models changed

``` bash
python manage.py makemigrations
python manage.py migrate
```

## Step 5 - Collect Static

``` bash
python manage.py collectstatic --noinput
```

## Step 6 - PythonAnywhere Dashboard

Go to **Web** and click **Reload**.

------------------------------------------------------------------------

# Quick Reference

  -----------------------------------------------------------------------
  What Changed                        Commands
  ----------------------------------- -----------------------------------
  Templates                           git pull → collectstatic → Reload

  Views                               git pull → collectstatic → Reload

  URLs                                git pull → collectstatic → Reload

  Models                              git pull → makemigrations → migrate
                                      → collectstatic → Reload

  New Package                         git pull → pip install -r
                                      requirements.txt → collectstatic →
                                      Reload
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# Useful Commands

``` bash
python manage.py check
python manage.py showmigrations
python manage.py collectstatic --noinput
```

------------------------------------------------------------------------

# Important Paths

Repository

    ~/Maa-Tara-HP-Gas

Virtual Environment

    ~/Maa-Tara-HP-Gas/.venv

Static

    /home/sumanchanda760/Maa-Tara-HP-Gas/staticfiles

Media

    /home/sumanchanda760/Maa-Tara-HP-Gas/media

WSGI

    /var/www/sumanchanda760_pythonanywhere_com_wsgi.py

Website

    https://sumanchanda760.pythonanywhere.com

------------------------------------------------------------------------

# Notes

-   PythonAnywhere Free uses SQLite.
-   MySQL requires a paid PythonAnywhere plan.
-   Always push to GitHub before deploying.
-   Always click Reload after deployment.
