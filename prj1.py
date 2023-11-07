from flask import Flask, request
from flask_restx import Api, Resource, fields, reqparse
from pymongo import MongoClient
import csv
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
from bson.objectid import ObjectId
import random
import string
import datetime
import requests 

app = Flask(__name__)
api = Api(app, version='1.0', title='Inventory API', description='API for Library Management System')
mongo_client = MongoClient('mongodb://localhost:27017/')
db = mongo_client['inventory_db']
collection = db['inventory_items']

archived_collection = db['archived_inventory']


inventory_model = api.model('Inventory', {
    'inv_logo': fields.String(required=True, description='Inventory logo'),
    'inv_name': fields.String(required=True, description='Inventory name'),
    'inv_description': fields.String(required=True, description='Inventory description'),
    'inv_type': fields.String(required=True, description='Inventory type'),
    'inv_blob': fields.String(required=True, description='Inventory blob'),
    'inv_archive_status': fields.Boolean(required=True, description='Inventory archive status'),
    'inv_copies': fields.Integer(required=True,description='Inventory number of Copies')
})

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'csv'

upload_model = api.model('UploadCSV', {
    'file': fields.Raw(required=True, description='CSV File')
})

upload_parser = reqparse.RequestParser()
upload_parser.add_argument('file', location='files', type=FileStorage, required=True)

def generate_inventory_id():
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    random_suffix = ''.join(random.choices(string.digits, k=4))
    return f'r{timestamp}{random_suffix}'

@api.route('/inventory/upload')
class UploadCSV(Resource):
    @api.expect(upload_parser)
    def post(self):
        args = upload_parser.parse_args()
        uploaded_file = args['file']

        try:
            data = csv.DictReader(uploaded_file.stream.read().decode('utf-8').splitlines())
            inserted_ids = []

            for row in data:
                row['inv_id'] = str(ObjectId())  # Generate unique inv_id

                # Convert inv_archive_status to boolean
                inv_archive_status = row.get('inv_archive_status', '').upper() == 'TRUE'
                row['inv_archive_status'] = inv_archive_status

                # Convert "inv_copies" to integer if possible
                inv_copies = row.get('inv_copies', '')
                try:
                    row['inv_copies'] = int(inv_copies)
                except ValueError:
                    row['inv_copies'] = 0  # Default to 0 if conversion to int fails

                if inv_archive_status:
                    result = collection.insert_one(row)
                else:
                    result = archived_collection.insert_one(row)

                inserted_ids.append(str(result.inserted_id))

            return {'message': 'Data uploaded successfully', 'inserted_ids': inserted_ids}, 200
        except Exception as e:
            return {'error': f'An error occurred while uploading data: {e}'}, 500

@api.route('/inventory/create')
class CreateInventory(Resource):
    @api.doc(description='Create a new inventory record', body=inventory_model)
    def post(self):
        try:
            inventory_data = api.payload
            inv_logo = inventory_data['inv_logo']
            inv_name = inventory_data['inv_name']
            inv_description = inventory_data['inv_description']
            inv_type = inventory_data['inv_type']
            inv_blob = inventory_data['inv_blob']
            inv_archive_status = inventory_data['inv_archive_status']
            inv_copies = inventory_data['inv_copies']
            
            inv_id = generate_inventory_id()  # Generate unique integer inv_id

            if inv_archive_status:
                result = collection.insert_one({
                    'inv_logo': inv_logo,
                    'inv_id': inv_id,
                    'inv_name': inv_name,
                    'inv_description': inv_description,
                    'inv_type': inv_type,
                    'inv_blob': inv_blob,
                    'inv_archive_status': inv_archive_status,
                    'inv_copies': inv_copies
                })
            else:
                result = archived_collection.insert_one({
                    'inv_logo': inv_logo,
                    'inv_id': inv_id,
                    'inv_name': inv_name,
                    'inv_description': inv_description,
                    'inv_type': inv_type,
                    'inv_blob': inv_blob,
                    'inv_archive_status': inv_archive_status,
                    'inv_copies': inv_copies
                })
            reduce_inventory_copies=(inv_id,inv_copies)

            inserted_id = str(result.inserted_id)
            return {'message': 'Inventory record created successfully', 'inventory_id': inv_id}, 201       
        except Exception as e:
            return {'message': f'Error: {e}'}, 500
        
@api.route('/inventory/view-all')
class DisplayAllInventory(Resource):
    def get(self):
        try:
            cursor = collection.find({'inv_archive_status': {'$ne': 'FALSE'}}, {'_id': 0})
            data = list(cursor)
            total_records = len(data)
            return {
                'total_records': total_records,
                'data': data
            }
        except Exception as e:
            return {'message': f'Error: {e}'}, 500



@api.route('/archived_inventory/view-all')
class DisplayAllArchivedInventory(Resource):
    def get(self):
        try:
            cursor = archived_collection.find({}, {'_id': 0})
            data = list(cursor)
            total_records = len(data)
            return {
                'total_records': total_records,
                'data': data
            }
        except Exception as e:
            return {'message': f'Error: {e}'}, 500

@api.route('/inventory/update/<string:inv_id>')
class UpdateResource(Resource):
    @api.expect(api.model('UpdateData', {
        'inv_logo': fields.String(required=True, description='Field 1'),
        'inv_name': fields.String(required=True, description='Field 2'),
        'inv_description': fields.String(required=True, description='Field 3'),
        'inv_type': fields.String(required=True, description='Field 4'),
        'inv_blob': fields.String(required=True, description='Field 5'),
        'inv_archive_status': fields.Boolean(required=True, description='Field 6'),
        'inv_copies': fields.Integer(required=True,description='Field 7'),
    }))
    def put(self, inv_id):
        try:
            data = api.payload
            result = collection.update_one({'inv_id': inv_id}, {'$set': data})
            if result.matched_count:
                return {'message': 'Record updated successfully'}, 200
            return {'message': 'Record not found'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500

@api.route('/inventory/delete/<string:inv_id>')
class DeleteResource(Resource):
    def delete(self, inv_id):
        try:
            result = collection.delete_one({'inv_id': inv_id})

            if result.deleted_count > 0:
                return {'message': 'Inventory item deleted successfully'}, 200
            else:
                return {'message': 'Failed to delete inventory item'}, 500

        except Exception as e:
            return {'message': f'Error: {e}'}, 500


           
@api.route('/inventory/delete-many')
class DeleteManyResource(Resource):
    @api.doc(description='Delete inventory records in bulk')
    @api.expect(api.model('BulkDeleteData', {
        'inventory_ids': fields.List(fields.String, required=True, description='List of inventory IDs to delete')
    }))
    def delete(self):
        data = api.payload
        inventory_ids = data.get('inventory_ids', [])

        if not inventory_ids:
            return {'error': 'No inventory IDs provided for deletion'}, 400

        try:
            result = collection.delete_many({'inv_id': {'$in': inventory_ids}})
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} inventory items deleted successfully'}, 200
            else:
                return {'message': 'No inventory items deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500
        

@api.route('/inventory/delete-all')
class DeleteAllResource(Resource):
    @api.doc(description='Delete all inventory records')
    def delete(self):
        try:
            result = collection.delete_many({})
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} inventory items deleted successfully'}, 200
            else:
                return {'message': 'No inventory items deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500
        

@api.route('/inventory/view')
class DisplayUploadedCSV(Resource):
    @api.doc(params={'page': 'Page number', 'limit': 'Items per page'})
    def get(self):
        try:
            page = int(request.args.get('page', 1))
            limit = int(request.args.get('limit', 10))
            total_records = collection.count_documents({})
            
            if page < 1:
                page = 1
            skip = (page - 1) * limit
            cursor = collection.find({}, {'_id': 0}).skip(skip).limit(limit)
            data = list(cursor)
            
            return {
                'page': page,
                'limit': limit,
                'total_records': total_records,
                'data': data
            }, 200
        except Exception as e:
            return {'message': f'Error: {e}'}, 500

@api.route('/archived_inventory/delete-all')
class DeleteAllArchivedInventory(Resource):
    @api.doc(description='Delete all archived inventory records')
    def delete(self):
        try:
            result = archived_collection.delete_many({})
            if result.deleted_count > 0:
                return {'message': f'{result.deleted_count} archived inventory items deleted successfully'}, 200
            else:
                return {'message': 'No archived inventory items deleted'}, 404
        except Exception as e:
            return {'message': f'Error: {e}'}, 500



def fetch_inventory_data():
    inventory_api_url = 'http://10.20.100.30:5001/inventory/view-all'
    #inventory_api_url = 'http://localhost:5001/inventory/view-all'  # Update URL as needed
    response = requests.get(inventory_api_url)
    inventory_data = response.json()
    return inventory_data


if __name__ == '__main__':
    app.run(debug=True, port=5001)
