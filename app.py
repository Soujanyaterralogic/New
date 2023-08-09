from flask import Flask, request
from flask_restx import Api, Resource, fields, reqparse, abort
from pymongo import MongoClient
from bson.objectid import ObjectId
from flasgger import Swagger
import datetime
import csv, os, random, string
from bson import json_util

app = Flask(__name__)
swagger = Swagger(app)
api = Api(app, version='1.0', title='Reservation API', description='API for Reservation Management')
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['reservationsample4_db4']
collection = db['reservations']

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

upload_model = api.model('UploadCSV', {
    'file': fields.Raw(required=True, description='CSV File')
})

def generate_reservation_id():
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.digits, k=4))
    return f'r{timestamp}{random_suffix}'

@api.route('/api/reservation/upload')
class UploadCSV(Resource):
    def post(self):
        if 'file' not in request.files:
            return {'error': 'No file part'}, 400
        file = request.files['file']
        if not file.filename:
            return {'error': 'No selected file'}, 400
        if file:
            # Clear existing data in the MongoDB collection
            collection.delete_many({})
            
            # Read and insert data from the CSV file into the MongoDB collection
            data = csv.DictReader(file.stream.read().decode('utf-8').splitlines())
            inserted_ids = []
            for row in data:
                result = collection.insert_one(row)
                inserted_ids.append(str(result.inserted_id))
            
            return {'inserted_ids': inserted_ids}, 201  # Fixed return statement
        
reservation_model = api.model('Reservation', {
    'reservation_id': fields.Integer(description='Reservation ID (Primary Key)'),
    'Reserved_user': fields.String(required=True, description='Name of the user making the reservation'),
    'Reservation_created_date': fields.DateTime(required=True, description='Date/Time of reservation creation'),
    'Inv_logo': fields.String(required=True, description='URL of the inventory logo'),
    'Inv_name': fields.String(required=True, description='Name of the inventory (URL)'),
    'Inv_description': fields.String(required=True, description='Description of the inventory'),
    'Reservation_status': fields.String(required=True, description='Status of the reservation'),
    'Reservation_status_comments': fields.String(description='Additional comments on the reservation status'),
    'Reservation_expiry_date': fields.DateTime(required=True, description='Date/Time of reservation expiry'),
    'Books': fields.List(fields.String, description='List of reserved items')  # Include the contents field
})

@api.route('/reservations')
class Reservations(Resource):
    @api.doc(params={'page': 'Page number', 'limit': 'Reservations per page'}, description='View all reservations')
    def get(self):
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 5))

        total_reservations = collection.count_documents({})

        if page < 1:
            page = 1

        skip = (page - 1) * limit

        reservations = list(collection.find({}).skip(skip).limit(limit))

        for reservation in reservations:
            reservation['_id'] = str(reservation['_id'])
            #reservation['Reservation_created_date'] = reservation['Reservation_created_date'].isoformat()
            #reservation['Reservation_expiry_date'] = reservation['Reservation_expiry_date'].isoformat()

        return {
            'page': page,
            'limit': limit,
            'total_reservations': total_reservations,
            'reservations': reservations
        }

"""
@api.route('/reservations')
class Reservations(Resource):
    @api.doc(params={'page': 'Page number', 'limit': 'Reservations per page'}, description='View all reservations')
    def get(self):
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 5))

        total_reservations = collection.count_documents({})

        if page < 1:
            page = 1

        skip = (page - 1) * limit

        reservations = list(collection.find({}).skip(skip).limit(limit))

        formatted_reservations = []
        for reservation in reservations:
            formatted_reservation = {
                '_id': str(reservation['_id']),
                'reservation_id': reservation['reservation_id'],
                'Reserved_user': reservation['Reserved_user'],
                'Reservation_created_date': reservation['Reservation_created_date'].isoformat(),
                'Inventory_logo': reservation['Inventory_logo'],
                'Inventory_name': reservation['Inventory_name'],
                'Inventory_description': reservation['Inventory_description'],
                'Reservation_status': reservation['Reservation_status'],
                'Reservation_status_comments': reservation['Reservation_status_comments'],
                'Reservation_expiry_date': reservation['Reservation_expiry_date'].isoformat(),
                'Books': reservation['Books']
            }
            formatted_reservations.append(formatted_reservation)

        return {
            'page': page,
            'limit': limit,
            'total_reservations': total_reservations,
            'reservations': formatted_reservations
        }
"""

@api.route('/reservations/<string:reservation_id>')
class Reservation(Resource):
    @api.doc(description='View a reservation by ID')
    def get(self, reservation_id):
        reservation = collection.find_one({'reservation_id': int(reservation_id)})
        if reservation:
            reservation['_id'] = str(reservation['_id'])
            return {'reservation': reservation} 
        return {'message': 'Reservation not found'}, 404
    
    @api.doc(description='Update a reservation by ID', body=reservation_model)
    def put(self, reservation_id):
        reservation_data = api.payload
        existing_reservation = collection.find_one({'reservation_id': int(reservation_id)})
        if not existing_reservation:
            return {'message': 'Reservation not found'}, 404
        
        result = collection.update_one({'reservation_id': int(reservation_id)}, {'$set': reservation_data})
        if result.modified_count == 1:
            return {'message': 'Reservation updated successfully'}
        return {'message': 'Failed to update reservation'}, 500
    
    @api.doc(description='Delete a reservation by ID')
    def delete(self, reservation_id):
        existing_reservation = collection.find_one({'reservation_id': int(reservation_id)})
        if not existing_reservation:
            return {'message': 'Reservation not found'}, 404
        
        result = collection.delete_one({'reservation_id': int(reservation_id)})
        if result.deleted_count == 1:
            return {'message': 'Reservation deleted successfully'}
        return {'message': 'Failed to delete reservation'}, 500


@api.route('/reservations/create')
class CreateReservation(Resource):
    @api.doc(description='Create a new reservation', body=reservation_model)
    def post(self):
        reservation_data = api.payload
        reservation_id = reservation_data.get('reservation_id')
        if not reservation_id:
            abort(400, error='reservation_id is required')

        existing_reservation = collection.find_one({'reservation_id': reservation_id})
        if existing_reservation:
            abort(400, error='A reservation with the same reservation_id already exists')

        user = reservation_data['Reserved_user']
        reservation_created_date = datetime.datetime.strptime(
            reservation_data['Reservation_created_date'], '%Y-%m-%dT%H:%M:%S.%fZ'
        )

        # Check if the user has reached the maximum reservations for this month
        current_month_start = reservation_created_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_month_end = current_month_start + datetime.timedelta(days=30)

        user_reservations_count = collection.count_documents({
            'Reserved_user': user,
            'Reservation_created_date': {
                '$gte': current_month_start,
                '$lt': current_month_end
            }
        })

        if user_reservations_count >= 3:
            abort(400, error='Maximum reservations reached for this month')

        new_reservation = {
            'reservation_id': reservation_id,
            'Reserved_user': user,
            'Reservation_created_date': reservation_created_date,
            'Inventory_logo': reservation_data['Inventory_logo'],
            'Inventory_name': reservation_data['Inventory_name'],
            'Inventory_description': reservation_data['Inventory_description'],
            'Reservation_status': 'Requested',
            'Reservation_status_comments': 'Waiting for approval',
            'Reservation_expiry_date': current_month_end,  # Expiry at the end of the month
            'Books': reservation_data['Books']
        }

        result = collection.insert_one(new_reservation)

        if result.inserted_id:
            inserted_id = str(result.inserted_id)
            return {'message': 'Reservation created successfully', '_id': inserted_id}, 201
        else:
            return {'message': 'Reservation creation failed'}, 500


if __name__ == '__main__':
    app.run(debug=True)
