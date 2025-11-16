const express = require('express')
const app = express()
const port = 3000

let service = process.env.SERVICE_NAME || 'default'
let html ="<html> <body><h1>Door Opener</h1><p>Open and close printer door!</p></body></html>"
app.get('/dooropener', (req, res) => res.send(html))

app.listen(port, () => console.log(`Door Opener - listening on port ${port}!`))