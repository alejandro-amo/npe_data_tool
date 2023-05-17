import time

import pandas
import requests
from bs4 import BeautifulSoup
import shutil
import os
import pandas as pd
import sys
from collections import OrderedDict
import argparse
from dotenv import load_dotenv

load_dotenv()
auth_username = os.getenv('AUTH_USERNAME')
auth_password = os.getenv('AUTH_PASSWORD')
google_api_key = os.getenv('GOOGLE_API_KEY')
# ↓ not only used as a base for other URLs, also used for first time HTTP auth in web server
baseurl = 'https://www.nopucesperar.cat/admin'
scrap_listitems_url = f'{baseurl}/?apt=establiment-llista&page=1&orig=establiment&ordre=&direccio=&&codi=&resultats=1'
# ↓ Note the %IDHERE% at the end. It's an URL template, not an URL ↓
scrap_itemsheet_url = f'{baseurl}/?apt=establiment-fitxa&id=%IDHERE%'
# scrap_itemsheet_url = f'https://127.0.0.1' #  <-- I use it to cause intentional network errors when testing ;)
update_data_url = f'{baseurl}/?apt=establiment-fitxa'
session = requests.Session()
folder_path = 'tmp'
output_path = 'output'
output_xlsx = 'output.xlsx'
xlsxpath = os.path.join(output_path, output_xlsx)
# ↓ used in scrapping routines to not accidentally cause a DoS attack on the server we scrap content from
throttling_value = 1
max_connection_strikes = 10
throttling_on_connection_strike = 2
list_of_parsed_values = []


def npe_authenticate():
    global session
    # Perform HTTP authentication to obtain cookies
    session.auth = (auth_username, auth_password)
    response = session.get(baseurl)
    # Check for HTTP errors
    response.raise_for_status()
    print("Authenticated in admin backoffice")


def get_amount_of_establishments() -> object:
    global session
    npe_authenticate()
    # Set cookies for subsequent requests
    cookies = session.cookies.get_dict()
    # Connect to the web page
    print('Getting the list of collaborator entities...')
    response = session.get(scrap_listitems_url)
    # Extract all links from the HTML content
    soup = BeautifulSoup(response.content, 'html.parser')
    links = soup.find_all('a', href=True)
    url_list = []
    for link in links:
        url = link['href']
        url_list.append(url)
    # Pick the links with the expression "establiment-fitxa" and store them in a dictionary
    for url in url_list:
        if '?apt=establiment-fitxa&orig=establiment&id=' in url:
            break
    max_id = url.replace('?apt=establiment-fitxa&orig=establiment&id=', '').replace(
        '&ordre=establiment_id&direccio=DESC&page=1&resultats=1&codi=&', '')
    amount = int(max_id)
    print(f'Total collaborator entities: {amount}')
    return amount


def dump_pages(until_id, from_id=None):
    if not isinstance(until_id, int):
        raise TypeError("The first parameter of dump_pages must be an integer")
    if from_id is not None and not isinstance(from_id, int):
        raise TypeError("When provided, the second parameter of dump_pages must be an integer")
    if from_id is None:
        from_id = 1
    range_low = from_id  # because 1st parameter of range() is inclusive
    range_high = until_id + 1  # because 2nd parameter of range() is exclusive
    print(f'Gathering pages from id {from_id} to id {until_id} (inclusive)...')

    # Ensure we have a tmp folder here.
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)

    from requests.exceptions import ConnectionError  # A patch to properly handle ConnectionErrors at Requests level

    # Download sheets of collaborators
    for i in range(range_low, range_high):
        get_url = scrap_itemsheet_url.replace('%IDHERE%', str(i))
        file_name = f"{i}.html"
        file_path = os.path.join(folder_path, file_name)
        print(f'Dumping {get_url} to {file_path}')
        scrapped_ok = False
        too_many_strikes = False
        connection_strikes = 0
        while not scrapped_ok and not too_many_strikes:
            try:
                response = session.get(get_url)
                print(f'DEBUG: HTTP status code: {response.status_code}')
                scrapped_ok = True
            except ConnectionError as e:
                connection_strikes += 1
                print(f'Warning: connection error {connection_strikes}/{max_connection_strikes}: {str(e)}')
                if connection_strikes >= max_connection_strikes:
                    too_many_strikes = True
                    break
                print(f'Waiting {throttling_on_connection_strike} secs after connection error...')
                time.sleep(throttling_on_connection_strike)
                print(f'Resuming after connection error...')
        if too_many_strikes:
            print(f'ERROR: Maximum amount of connection errors reached ({str(max_connection_strikes)}).')
            print('Consider increasing the throttling value or the amount of maximum connection problems.')
            exit(1)
        # Now, we store the contents of response in file_path
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(response.text)
        time.sleep(throttling_value)


def soup_to_values(soup):
    form_values = {}
    for input_tag in soup.find_all('input'):
        form_values[input_tag.get('name')] = input_tag.get('value')

    for select_tag in soup.find_all('select'):
        try:
            form_values[select_tag.get('name')] = select_tag.find('option', selected=True).get('value')
        except AttributeError as e:
            print(f'Omitting this page because it has empty data in form (inactive collaborator)')
            return None
    # print(form_values)
    this_id = form_values['id']
    this_name = form_values['input[nom]']
    this_type = form_values['input[tipus_fk]']
    this_address = form_values['input[adreca]']
    this_postalcode = form_values['input[cp]']
    this_city = form_values['input[poblacio]']
    this_phone = form_values['input[telefon]'].replace('.', '').replace(' ', '').replace('·', '')
    this_email = form_values['input[email]']
    this_web = form_values['input[web]']
    this_gpslat = form_values['input[latitud]']
    this_gpslong = form_values['input[longitud]']
    final_data = {'id': this_id, 'name': this_name, 'type': this_type, 'address': this_address,
                  'postalcode': this_postalcode,
                  'city': this_city, 'phone': this_phone, 'email': this_email, 'web': this_web,
                  'lat': this_gpslat, 'long': this_gpslong}
    # print(final_data)
    return final_data


def parse_single_page(page_path):
    # check if the file exists
    if not os.path.exists(page_path):
        raise FileNotFoundError(f"HTML file not found at {page_path}")

    # read the file contents
    print(f'Parsing {page_path}...')
    with open(page_path, "r", encoding='utf-8') as f:
        html = f.read()

    # create a BeautifulSoup object from the HTML
    soup = BeautifulSoup(html, "html.parser")
    return soup_to_values(soup)


def parse_pages():
    global list_of_parsed_values
    html_files = [file for file in os.listdir(folder_path) if file.endswith('.html')]
    for file in html_files:
        page_values = parse_single_page(os.path.join(folder_path, file))
        if page_values:
            list_of_parsed_values.append(page_values)
    # Create a Pandas DataFrame from the list of dictionaries
    print(f'Dumping to excel file {xlsxpath}...')
    df = pd.DataFrame(list_of_parsed_values)
    # Export the DataFrame to an Excel file
    df.to_excel(xlsxpath, index=False)
    print('Exported.')
    exit(0)


def build_weird_npe_form_data(**kwargs):
    return_value = OrderedDict()
    idnotfound = True  # we always need to check if there is a value for 'input[id]' which defines what item to update.
    for key, value in kwargs.items():
        # some shorthands for convenience. you can pass "id" and it will be parsed as in the original form: "input[id]"
        if key == 'id':
            key = 'input[id]'
        if key == 'entitat_fk':
            key = 'input[entitat_fk]'
        if key == 'tipus_fk':
            key = 'input[tipus_fk]'
        if key == 'nom':
            key = 'input[nom]'
        if key == 'adreca':
            key = 'input[adreca]'
        if key == 'cp':
            key = 'input[cp]'
        if key == 'poblacio':
            key = 'input[poblacio]'
        if key == 'telefon':
            key = 'input[telefon]'
        if key == 'email':
            key = 'input[email]'
        if key == 'web':
            key = 'input[web]'
        if key == 'latitud':
            key = 'input[latitud]'
        if key == 'longitud':
            key = 'input[longitud]'
        if key == 'actiu':
            key = 'input[actiu]'
        if key == 'adreca':
            key = 'input[adreca]'
        return_value[key] = (None, value)
        if key == 'input[id]':
            idnotfound = False
    if idnotfound:
        print('ERROR: we need at least the value of id to know what item are we going to update!')
        exit(1)
    return return_value


def update_sheet_data(npe_id, **kwargs):
    kwargs_str = ', '.join(f"{key}={value}" for key, value in kwargs.items())
    print(f'DEBUG: Updating item {npe_id} with following parameters: {kwargs_str}')
    global session
    # npe_authenticate()
    files = build_weird_npe_form_data(id=npe_id, **kwargs)
    try:
        response = session.post(update_data_url, files=files)
        print(f'Update of item {npe_id} completed without errors.')
        return True
    except requests.exceptions.RequestException as e:
        # Handle connection or request errors
        print(f'Error updating item {npe_id}: {str(e)}')
        print(f'Returned HTTP code {response.status_code}.')
        return False

def enhance_establishment_data(name, address, postalcode, city, latitude, longitude):
    # Create the request URL with the provided parameters
    url = f'https://maps.googleapis.com/maps/api/geocode/json?address={name}, {address}, {postalcode}, {city}&latlng={latitude},{longitude}&key={google_api_key}'

    try:
        # Send a GET request to the Geocoding API
        response = requests.get(url)
        data = response.json()

        if response.status_code == 200 and data['status'] == 'OK':
            # Extract the enhanced/corrected data from the API response
            result = data['results'][0]
            # print(f'Debug - Google API results: {result}')
            # enhanced_name = result['name']
            enhanced_address = result['formatted_address']
            enhanced_postalcode = None  # We extract it later
            enhanced_city = None  # We extract it later
            enhanced_latitude = result['geometry']['location']['lat']
            enhanced_longitude = result['geometry']['location']['lng']
            # Now, the stuff that needs iteration to be extracted
            for component in result['address_components']:
                if 'postal_code' in component['types']:
                    enhanced_postalcode = component['long_name']
                elif 'locality' in component['types']:
                    enhanced_city = component['long_name']
            for component in result['address_components']:
                if 'postal_code' in component['types']:
                    enhanced_postal_code = component['long_name']
                if 'locality' in component['types']:
                    enhanced_city = component['long_name']

            # Return the enhanced/corrected data
            return {
                'address': enhanced_address,
                'postalcode': enhanced_postalcode,
                'city': enhanced_city,
                'lat': enhanced_latitude,
                'long': enhanced_longitude
            }
        else:
            if data['status'] == 'ZERO_RESULTS':   # Well, nobody's perfect.
                print('INFO: No results for this search. Returning empty dictionary.')
                return {'address': None, 'postalcode': None, 'city': None, 'lat': None, 'long': None }
            if response.status_code != 200:
                print(f'ERROR: Google API HTTP status code was not OK ({response.status_code})')
                print(f'Google API response was: {str(response.text)}')
                exit(1)

    except requests.exceptions.RequestException as e:
        # Handle connection or request errors
        print(f'Error: {str(e)}')
        return None


def enrich_establishment_addresses():
    print(f'Loading NoPucEsperar data in {xlsxpath}...')
    try:
        df = pd.read_excel(xlsxpath)
    except:
        print('Error loading xlsx file with scrapped data from NoPucEsperar.')
        print('You should perfom scrape command in order to have a working Excel file.')
        exit(1)
    # Sort by id
    df.sort_values('id', inplace=True)
    new_address = []
    new_postalcode = []
    new_city = []
    new_lat = []
    new_long = []
    for index,row in df.iterrows():
        id = row['id']
        name = row['name']
        address = row['address']
        postalcode = row['postalcode']
        city = row['city']
        lat = row['lat']
        long = row['long']
        print(f'Querying Google API to enhance address and coordinates of establishment #{id}...')
        enriched_data = enhance_establishment_data(name, address, postalcode, city, lat, long)
        if not enriched_data:
            print('After querying Google API, we got no data. Please check connection or API key errors.')
            exit(1)
        # print(f'Debug - Obtained result from Google API: {enriched_data}')
        new_address.append(enriched_data['address'])
        new_postalcode.append(enriched_data['postalcode'])
        new_city.append(enriched_data['city'])
        new_lat.append(enriched_data['lat'])
        new_long.append(enriched_data['long'])
    df['new_address'] = new_address
    df['new_postalcode'] = new_postalcode
    df['new_city'] = new_city
    df['new_lat'] = new_lat
    df['new_long'] = new_long
    return df


def mass_update_npe_from_xlsx_data():
    print(f'Loading NoPucEsperar data in {xlsxpath}...')
    try:
        df = pd.read_excel(xlsxpath)
    except:
        print('Error loading xlsx file with scrapped data from NoPucEsperar.')
        print('You should perfom scrape command in order to have a working Excel file.')
        exit(1)
    # Sort by id
    df.sort_values('id', inplace=True)
    df.fillna('', inplace=True)
    df = df.astype(str)
    df['id'] = pd.to_numeric(df['id'])
    for index,row in df.iterrows():
        id = row['id']
        print(f'Updating sheet of establishment with id {id} in NoPucEsperar...')
        name = row['name']
        address = row['address']
        postalcode = row['postalcode']
        city = row['city']
        phone = row['phone']
        email = row['email']
        web = row['web']
        lat = row['lat']
        long = row['long']
        _ = update_sheet_data(id,
                              nom=name,
                              adreca=address,
                              cp=postalcode,
                              poblacio=city,
                              telefon=phone,
                              email=email,
                              web=web,
                              latitud=lat,
                              longitud=long,
                              actiu=1)
        time.sleep(throttling_value)


def get_googleplaces_info(search_term):
    # Format the name and address parameters for the API request
    search_term = search_term.replace(' ', '+')

    # Create the API request URL
    url = f'https://maps.googleapis.com/maps/api/place/findplacefromtext/json?input={search_term}&fields=name,business_status&inputtype=textquery&key={google_api_key}&language=es'
    # print(f'DEBUG - URL: {url}')

    try:
        # Send the request to the Google Places API
        response = requests.get(url)
        data = response.json()
        # Check if the request was successful
        status = data['status']
        if response.status_code == 200 and status == 'OK':
            # Return the establishment data
            result = []
            result.append(len(data['candidates']))  # 1st element will always be the amout of items we have
            for candidate in data['candidates']:
                result.append(candidate)
            return result
        elif status == 'ZERO_RESULTS':
            return [0]
        else:
            if 'error_message' in response:
                error_message = response['error_message']
            else:
                error_message = '(none)'
            print(f'Warning: Google findplace request status: {status}. Error message: {error_message}')
            return None
    except requests.exceptions.RequestException as e:
        # Handle connection errors
        print('Error connecting to the API:', e)
        return None


def enrich_establishment_statuses():
    print(f'Loading NoPucEsperar data in {xlsxpath}...')
    try:
        df = pd.read_excel(xlsxpath)
    except:
        print('Error loading xlsx file with scrapped data from NoPucEsperar.')
        print('You should perfom scrape command in order to have a working Excel file.')
        exit(1)
    # Sort by id
    df.sort_values('id', inplace=True)
    # Google findplaces API related fields. Used to determine the status of the establishment (did it close?)
    # We take up to 3 candidates, but probably first will be the right one most of the time. We get the names to verify.
    candidate1names = []
    candidate1statuses = []
    candidate2names = []
    candidate2statuses = []
    candidate3names = []
    candidate3statuses = []

    for index,row in df.iterrows():
        id = row['id']
        name = row['name']
        address = row['address']
        postalcode = row['postalcode']
        city = row['city']
        print(f'Querying Google API to know about the status of establishment #{id}...')
        enriched_data = get_googleplaces_info(f'{name}, {address}, {postalcode} {city}')
        if not enriched_data:
            print('After querying Google API, we got no data. Please check connection or API key errors.')
            enriched_data = [0]
            # exit(1)
        print(f'Debug - Values extracted from Google findplaces API: {enriched_data}')
        candidate1name = None
        candidate1status = None
        candidate2name = None
        candidate2status = None
        candidate3name = None
        candidate3status = None
        if enriched_data[0] > 0:  # at least one candidate
            candidate1name = enriched_data[1]['name']
            if 'business_status' in enriched_data[1]:
                candidate1status = enriched_data[1]['business_status']
        if enriched_data[0] > 1:  # at least two candidates
            candidate2name = enriched_data[2]['name']
            if 'business_status' in enriched_data[2]:
                candidate2status = enriched_data[2]['business_status']
        if enriched_data[0] > 2:  # three or more candidates (we only get until the 3rd)
            candidate3name = enriched_data[3]['name']
            if 'business_status' in enriched_data[3]:
                candidate3status = enriched_data[3]['business_status']
        candidate1names.append(candidate1name)
        candidate1statuses.append(candidate1status)
        candidate2names.append(candidate2name)
        candidate2statuses.append(candidate2status)
        candidate3names.append(candidate3name)
        candidate3statuses.append(candidate3status)

    df['candidate1name'] = candidate1names
    df['candidate1status'] = candidate1statuses
    df['candidate2name'] = candidate2names
    df['candidate2status'] = candidate2statuses
    df['candidate3name'] = candidate3names
    df['candidate3status'] = candidate3statuses
    return df

def parse_parameters():
    parser = argparse.ArgumentParser()

    # Define the arguments
    parser.add_argument('command', type=str, help='Action to be performed (scrap, enrich, enrich2, update, massupdate). Mandatory.')
    parser.add_argument('--id', type=int, help='Id of the element we want to update. Mandatory if command is "update".')
    parser.add_argument('--entitat_fk', type=int, help='Numerical value defining who registered this item. 1 is of ACCU Catalunya and it currently does not change.')
    parser.add_argument('--tipus_fk', type=int, help='Numerical value defining type of entity. 1 is generic and most common, 2 for hospitals, 3 for city halls.')
    parser.add_argument('--nom', type=str,
                        help='Name of the establishment.')
    parser.add_argument('--adreca', type=str,
                        help='Address of the establishment.')
    parser.add_argument('--cp', type=str,
                        help='Postal code of the establishment.')
    parser.add_argument('--telefon', type=str,
                        help='Telephone of the establishment.')
    parser.add_argument('--email', type=str,
                        help='Email of the establishment.')
    parser.add_argument('--web', type=str,
                        help='Url of the establishment''s web site.')
    parser.add_argument('--latitud', type=str,
                        help='GPS lat. of the establishment.')
    parser.add_argument('--longitud', type=str,
                        help='GPS long. of the establishment.')
    parser.add_argument('--actiu', type=int,
                        help='Whether the establishment is active (1) or not (0).')

    # Parse the arguments
    args = parser.parse_args()

    # Create a dictionary of the provided arguments
    arguments = {
        'command': args.command,
        'id': args.id,
        'entitat_fk': args.entitat_fk,
        'tipus_fk': args.tipus_fk,
        'nom': args.nom,
        'adreca': args.adreca,
        'cp': args.cp,
        'telefon': args.telefon,
        'email': args.email,
        'web': args.web,
        'latitud': args.latitud,
        'longitud': args.longitud,
        'actiu': args.actiu
    }
    if arguments['command'] == 'update':
        print('Command: update')
    if arguments['command'] == 'update' and arguments['id'] is None:
        print('Error: when command is "update", specifying --id is mandatory')
        exit(1)

    return arguments


if __name__ == '__main__':
    # print(sys.argv)
    parameters = parse_parameters()
    if 'command' in parameters:
        if parameters['command'] == 'update':
            npe_id = parameters['id']  # use 'id=4927' for testing purposes
            npe_authenticate()  # test auth, raise error if failed
            update_sheet_data(npe_id, entitat_fk=parameters['entitat_fk'], tipus_fk=parameters['tipus_fk'],
                              nom=parameters['nom'], adreca=parameters['adreca'], cp=parameters['cp'],
                              telefon=parameters['telefon'], email=parameters['email'], web=parameters['web'],
                              latitud=parameters['latitud'], longitud=parameters['longitud'], actiu=parameters['actiu'])
        elif parameters['command'] == 'scrap':
            max_id = get_amount_of_establishments()
            dump_pages(max_id, 1)  # TODO: provide control of start_from parameter via command line
            parse_pages()
        elif parameters['command'] == 'enrich':
            results = enrich_establishment_addresses()
            results.to_excel(xlsxpath)
        elif parameters['command'] == 'enrich2':
            results = enrich_establishment_statuses()
            results.to_excel(xlsxpath)
            # results = get_googleplaces_info('EL MUSEU DEL VI, Cort Reial, 4, Girona')
            # print(results)
        elif parameters['command'] == 'massupdate':
            npe_authenticate()  # test authentication, raise error if failed
            mass_update_npe_from_xlsx_data()
        else:
            print('Unknown command specified!')
    else:
        print('No command specified!')
    print('Finished')
