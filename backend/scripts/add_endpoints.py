import re 
 
with open('routes/api_v1.py', 'r') as f: 
    content = f.read() 
 
# Add data-status endpoint 
if '/data-status' not in content: 
    insert_point = content.find("@api_v1.route('/docs')") 
    new_code = ''' 
@api_v1.route('/data-status', methods=['GET']) 
def data_status(): 
    try: 
        latest_date = db_manager.execute_query("SELECT MAX(date) as latest_date FROM climate_records") 
        total = db_manager.execute_query("SELECT COUNT(*) as count FROM climate_records") 
        years = db_manager.execute_query("SELECT DISTINCT year FROM climate_records ORDER BY year") 
        return success_response({ 
            "latest_date": latest_date[0]['latest_date'].isoformat() if latest_date and latest_date[0]['latest_date'] else None, 
            "total_records": total[0]['count'] if total else 0, 
            "years_coverage": [y['year'] for y in years] if years else [] 
        }) 
    except Exception as e: 
        return error_response(str(e), 500) 
''' 
    content = content[:insert_point] + new_code + content[insert_point:] 
 
# Write the file 
with open('routes/api_v1.py', 'w') as f: 
    f.write(content) 
 
print("? Endpoints added successfully!") 
