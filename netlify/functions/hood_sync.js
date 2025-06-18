exports.handler = async function(event, context) {
  return {
    statusCode: 200,
    body: JSON.stringify({
      message: "Hood-Sync Test Function",
      timestamp: new Date().toISOString()
    })
  };
} 