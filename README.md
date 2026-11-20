# Personal Finance Tracker

A personal finance web application built with Python, Flask, and SQLAlchemy to track income, expenses, and monthly budgets.

## Features

- User registration and login with password hashing
- Add, edit, and delete transactions
- Filter transactions and view financial summaries
- Monthly category budgets and spending alerts
- Charts for spending categories and monthly trends
- CSV transaction export
- CSRF protection

## Technologies

Python, Flask, SQLAlchemy, Flask-Login, Flask-WTF, SQLite, Tailwind CSS, and Chart.js.

## Run locally

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

Install dependencies and start the application:

```bash
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:4848 in your browser, then register an account.

SQLite is used by default, and the database is created automatically. An alternative database can be configured using the DATABASE_URL environment variable.

## Project structure

- app.py — application routes and configuration
- models.py — database models
- templates/ — HTML templates
- requirements.txt — Python dependencies

## Status

Student project intended for local demonstration. The current version does not include automated tests or savings goals. Flask's development server is not intended for production use.
