# Use the official Python image
FROM python:3.8

# Set the working directory
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy the application code into the container
COPY . .

# Expose the port that the app will run on
EXPOSE 5001

# Define the command to run your application
CMD ["python", "prj1.py"]
