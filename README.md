📊 Predictive Analytics SaaS with Machine Learning

This project is a SaaS backend focused on data analysis and generating predictions from spreadsheets submitted by the user.

The application allows data upload, automatic training of Machine Learning models, and comparison of performance metrics via REST API.

🚀 Objective

To provide a simple and scalable solution for:

Uploading spreadsheets (.csv)

Data processing and validation

Supervised automated model training

Evaluation of statistical metrics

Comparison between real data and predictions

Structured return via API

🏗 Architecture

The system was developed using:

FastAPI – REST API construction

scikit-learn – Model training and evaluation

pandas – Data manipulation and processing

NumPy – Numerical operations

JWT-based authentication

Modular architecture separating:

API layer

Business logic layer

Machine Learning module

Model persistence

🔄 Application Flow

User submits spreadsheet (.csv)

System validates and processes the data

Model is automatically trained

Performance metrics are Calculated data

API returns:

Prediction results

Statistical metrics

Comparison between actual and predicted values

📈 Features

Secure file upload

Automated ML pipeline

Separation of responsibilities (API / ML / Data)

Data validation

Statistical performance evaluation

Structure prepared for future expansion (front-end or new models)

🎯 Target Audience

Small businesses or professionals who want to test statistical predictions in a simple way, without having to manually configure Machine Learning pipelines.

🔮 Upcoming Developments

Dedicated frontend interface

User plan control

Historical persistence of analyses

Multiple configurable models