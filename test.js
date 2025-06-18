const { handler } = require('./netlify/functions/hood_sync');

// Setze Umgebungsvariablen für den Test
process.env.FEED_URL = "https://example.com/feed.csv";
process.env.HOOD_PASSWORD = "test_password";
process.env.ACCOUNT_NAME = "test_account";
process.env.HOOD_ENDPOINT = "https://www.hood.de/api.htm";
process.env.TEST_CSV = "mpnr,name,price,stock,description,image1\n12345,Test Produkt,19.99,10,Testbeschreibung,https://example.com/image.jpg";

// Führe die Funktion aus
async function test() {
  try {
    const result = await handler({});
    console.log('Statuscode:', result.statusCode);
    console.log('Response:', result.body);
  } catch (error) {
    console.error('Fehler:', error);
  }
}

test(); 