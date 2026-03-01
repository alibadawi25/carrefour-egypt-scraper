# Use the official Apify Python image
FROM apify/actor-python:3.11

# Copy source code and install dependencies
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the source code
COPY . ./

# Run the actor
CMD python -m src