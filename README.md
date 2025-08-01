# Label Backend API

This project is a backend API built with **Flask** and **PostgreSQL**. It is used to manage user login, photo evaluation, and price tag check results.

## Features

- User login with token (JWT)
- Save image check results (missing, incorrect, duplicate, etc.)
- Save price tag evaluation results
- Get daily file check count per user
- Secure routes with token authentication
- CORS enabled for frontend access
- Database connection using `psycopg2`

## Technologies

- Python 3
- Flask
- PostgreSQL
- psycopg2
- JWT
- Dotenv

## Requirements

- Python 3.9+
- PostgreSQL database
- Environment file `.env`
