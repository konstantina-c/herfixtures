export default async function handler(req, res) {
  // Only allow POST requests
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  // Allow requests from your domain only
  res.setHeader('Access-Control-Allow-Origin', 'https://herfixtures.com');
  res.setHeader('Access-Control-Allow-Methods', 'POST');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  const { email, league } = req.body;

  // Basic email validation
  if (!email || !email.includes('@')) {
    return res.status(400).json({ error: 'Valid email required' });
  }

  try {
    const response = await fetch(
      'https://api.beehiiv.com/v2/publications/pub_f9b23a38-5505-4cd0-a8d8-3458ced05820/subscriptions',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${process.env.BEEHIIV_API_KEY}`
        },
        body: JSON.stringify({
          email: email,
          reactivate_existing: true,
          send_welcome_email: true,
          custom_fields: [
            { name: 'Favourite League or Team', value: league || '' }
          ]
        })
      }
    );

    if (response.ok || response.status === 201) {
      return res.status(200).json({ success: true });
    } else {
      const error = await response.json();
      console.error('Beehiiv error:', error);
      return res.status(500).json({ error: 'Subscription failed' });
    }
  } catch (err) {
    console.error('Server error:', err);
    return res.status(500).json({ error: 'Server error' });
  }
}
