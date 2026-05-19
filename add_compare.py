import re 
 
with open('routes/api_v1.py', 'r') as f: 
    content = f.read() 
 
if "compare" not in content: 
    insert_point = content.find("@api_v1.route('/docs')") 
 
    compare_code = ''' 
@api_v1.route('/compare', methods=['GET']) 
def compare_variables(): 
    \"\"\"Compare multiple variables over time\"\"\" 
    try: 
        variables = request.args.getlist('variables') 
        start_year = request.args.get('start_year', 2015, type=int) 
        end_year = request.args.get('end_year', 2025, type=int) 
        province = request.args.get('province') 
        allowed_vars = ['Rainfall_mm', 'NDVI', 'Temp_Max_C', 'Temp_Min_C', 'SoilMoisture_pct', 'CropYield_kg_ha'] 
        if not variables: 
            return success_response({'available_variables': allowed_vars, 'usage': '/api/v1/compare?variables=Rainfall_mm,NDVI'}) 
        variables = [v for v in variables if v in allowed_vars] 
        if not variables: 
            return error_response('No valid variables', 400) 
        df = load_data_from_db() 
        if df is None or df.empty: 
            return empty_response('No data') 
        if province: 
            df_filtered = df_filtered[df_filtered['province'] == province] 
        result = {'years': list(range(start_year, end_year + 1))} 
        for var in variables: 
            if var in df_filtered.columns: 
                grouped = df_filtered.groupby('year')[var].mean().reset_index() 
                result[var] = [safe_round(val) for val in grouped[var].tolist()] 
            else: 
                result[var] = [] 
        return success_response(result) 
    except Exception as e: 
        logger.error(f"Compare error: {e}") 
        return error_response(str(e), 500) 
''' 
 
    content = content[:insert_point] + compare_code + content[insert_point:] 
    with open('routes/api_v1.py', 'w') as f: 
        f.write(content) 
    print("Compare endpoint added successfully!") 
else: 
    print("Compare endpoint already exists") 
