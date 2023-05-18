<div style="text-align: center" align="center">
    <h1>Data Tool for 🚽 NPE App 🚽 </h1>
    <p>
        <strong>A practical example on how to use Python to cover several needs<br>
and solve several problems of an old App's data lifecycle:
<br>exporting, cleaning, correcting, enriching and reimporting. En masse or punctually.
</strong>
    </p>
    <br>
    <img src="https://www.nopuedoesperar.es/upload/apartat/esp.jpg" alt="Header Image">
    <br>
    <p style="text-align: center">
        <a href="#what-is-npe">What is NPE?</a> •
        <a href="#what-data-challenge-does-npe-face">What data challenge does NPE face?</a> •
        <a href="#usage">Usage</a> •
        <a href="#license">License</a> •
        <a href="#questions-similar-challenges">Questions? Similar challenges?</a>
    </p>
    <br>
    <p>
        <em>NOTE: This tool is published for showcasing purposes and it's not intended for public use (it requires credentials in the admin backoffice of a private App)<br>
        However, you can take a look at the code to grab snippets of code and learn about data scrapping/updating in complex situations. If it was useful for you in a way or another, please star ⭐️ this repository and send me an email to tell your story :)</em>
    </p>
    <br>
    <p style="text-align: center">
        <img alt="GitHub last commit" src="https://img.shields.io/github/last-commit/alejandro-amo/npe_data_tool">
        <img alt="GitHub license" src="https://img.shields.io/github/license/alejandro-amo/npe_data_tool">
        <img alt="Total cost of the project: 150€" src="https://img.shields.io/badge/Total%20cost%20(API usage)-150€-blue"> 
        <img alt="Total development time: 2 days" src="https://img.shields.io/badge/Total%20development%20time-2%20days%20(staff%20training%20apart)-blue">
    </p>
</div>


## What is NPE? 

NoPucEsperar (I Can't Wait, "NPE" for short) is an initiative developed by the Association of Crohn's Disease and Ulcerative Colitis Patients of Catalonia (ACCU Catalonia) and the Inflammatory Bowel Disease (IBD) Unit of the University Hospital of Girona. It aims to assist individuals with inflammatory bowel diseases and other medical conditions that require urgent restroom access.

The project provides NPE cards to eligible patients, allowing them to quickly and freely access restrooms in various locations (mostly commercial establishments that join the project to support the patients). 
The initiative seeks to improve the quality of life for patients by offering convenient restroom access and raising awareness about inflammatory bowel diseases.

## What data challenge does NPE face?

The challenge that NPE faces as a project is two folded:
- On one hand, maintaining data of thousands of commercial establishments updated is very difficult. The volunteers recruit local shops within their areas of influence but once this data is registered in NPE's database, there is no efficient way of knowing if the establishment has closed, if the establisment staff has changed (and hence their supporting position regarding NPE) or if they have changed the name.
- On the other hand, the data maintenance backend is slow, barely usable, prone to errors and very limited in features; it does not sanitize inputs nor helps the NPE staff having good quality data in any other way. Human error caused by untrained people and lack of a data policy has also been accumulating for years and the data of supporting local businesses has become potentially unreliable, requiring an high amount of effort to review, verify and correct, which is unbearable for the small staff at the project. 

On top of that, the original developers refuse to provide direct access to database, and they want to charge even for fixing some bugs detected, so collaboration with original developers in this case is a no-no.

So I got down to work and started developing an external tool that could properly interoperate with the administration backoffice by means of scrapping the web pages and mimicking the original HTTP requests involved in each data operation.
The goal is having a tool that could be used to provide data caring functionality and help this project solve the technical debt they were carrying.

## Usage
### First stage: Downloading data to local filesystem
A simple run of `python main.py scrap` will connect to the admin backoffice and start scraping all data from establishments in the database.
1. It will populate the `tmp` folder with .html files named as the numerical ID of the establishment, autocalculating which is the last/highest ID available.
2. Once all html files are downloaded, it will parse and extract all the information in data fields to a dataframe.
3. Finally, it will dump the dataframe to an MS excel file in `output\output.xlsx` so the NPE staff can work on data maintenance very agilely and with no additional tools.

### Next stage: Correcting missing/wrong GPS/address data
Working with an excel file enabled the NPE staff at NPE to correct and review more data in much less time, but that doesn't solve all the problems. At this point we still need to complete and correct missing or wrong GPS data about the establishments stored in database, and searching for it manually using Google maps is simply unbearable.

So, with just a run of `python main.py enrich`, the program:

1. Reads the xlsx file generated previously.
2. Iterates through the rows in MS Excel file, extracting name and address of each establishment and asking **Google Maps API** in order to get a second opinion about the GPS coordinates and address of the place.
3. Then new columns are added to the original xlsx file, so a human being can review them and decide to use the proposals provided by Google (just by coping the contents of the field i.e. `new_lat` to `lat`, `new_name` to `name`, etc.). We did it this way because we wanted the NPE staff to keep full control of changes, so they can review them manually (it is a great improvement in time and effort, still!)

### Next stage: Obtaining additional info about operational status of the businesses

At this point we have corrected addresses, postal codes, GPS coords and all the necessary information... 

...except that we have no idea whether if the establishment is still operating or if it has been temporarily/definitely closed. This is important for the users of NPE App because they expect to find reliable data when they are in urgent need of using a toilet!

So, with just a run of `python main.py enrich2`, the program iterates through all the information in xlsx again, this time querying the `findPlaceFromText` endpoint of Google Places API and enriching the data with a list of up to three possible candidates in Google Places' database as well as their operational status (open, closed temporarily, closed permanently). Again, we leave up to the NPE staff the task of reviewing the information and decide if it's accurate (most of the time, the first candidate proposed by Google matches the establishment we are looking for).

### Last stage: Uploading the data from the edited xlsx file back to the App

Obviously, this tool has such capability in order to apply all the changes made in previous stages. 

Instead of relying on POST requests with well-structured `x-www-form-urlencoded`, the NPE admin backoffice features a weird API that expects the data to be sent in `multipart/form-data`, with a suboptimal data structure that sends many empty or repeated values and silently ignoring any form-data part sent when a `filename` in its header. It took some time and proper usage of [Postman's interceptor ❤️](https://chrome.google.com/webstore/detail/postman-interceptor/aicmkgpgakddgnaphhhpliifpcfhicfo) to figure out the correct way of constructing and sending the requests in order to get a successful result.

The program simply needs to be run with `python main.py massupdate` to push the data back to the server once we have been working on it.

### Optionally: minor, quick changes in single items

For minor corrections and quick updates, I have also implemented a command line inside the tool so the NPE staff at NPE can update data really quickly. Its usage is also simple:


`python main.py edit --id=123 --what_to_change=value_to_set --what_to_change=value_to_set ...`

Where id is mandatory (we need it to know what are we trying to update, of course), what_to_change can be any of the following (Spaces are ok as long as the expression is "appropriately quoted"):

- `tipus_fk`: A numerical argument specifying the type of establishment, from one to three. NPE keeps distinction between regular establishments, health centers and city halls.
- `nom`: Name of the establishment.
- `adreca`: Address of the establishment.
- `cp`: Postal code.
- `telefon`: Phone number.
- `email`: Email address.
- `web`: Website of the establishment.
- `latitud` and `longitud`: GPS coords. Decimal point is expected to be the period sign.
- `actiu`: A value of `1` sets the establishment as visible and operational. A value of `0` makes it not appear to users in listings.

## License
CC-BY 4.0. You have a copy of the license here: [license](license)

## Questions? Similar challenges?
📧 Drop me an email then: [hello@alejandroamo.eu](mailto:hello@alejandroamo.eu)
