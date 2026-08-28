app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok' });
});
