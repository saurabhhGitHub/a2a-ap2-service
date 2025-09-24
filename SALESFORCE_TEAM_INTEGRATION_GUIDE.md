# Salesforce Team Integration Guide

## 🎯 What You Need to Integrate With

Your **Collections Agent Backend** is now ready for integration! Here's what you need to know:

## 📋 **Integration Checklist for Salesforce Team**

### ✅ **What's Already Built (Ready for You)**

1. **Core Processing Engine** ✅
   - Invoice collection processing
   - Payment orchestration via A2A/AP2
   - Audit logging and compliance
   - Status tracking and updates

2. **Integration APIs** ✅
   - Salesforce webhook endpoints
   - Slack approval workflows
   - Status monitoring APIs
   - A2A agent communication

3. **Documentation** ✅
   - Complete API documentation
   - Integration examples
   - Error handling guide

### 🔧 **What You Need to Build**

1. **Salesforce Agentforce Integration**
   - Trigger collection requests to our backend
   - Monitor overdue invoices
   - Update invoice statuses

2. **Slack App Integration**
   - Interactive messages for approvals
   - Slash commands for status checks
   - Real-time notifications

## 🚀 **Quick Start Integration**

### **Step 1: Send Collection Request to Our Backend**

```javascript
// From Salesforce Agentforce
const response = await fetch('https://your-backend.com/api/v1/integration/salesforce/webhook/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'your-api-key'
  },
  body: JSON.stringify({
    invoice_id: 'INV-2024-001',
    amount: 10230.00,
    currency: 'USD',
    customer_id: 'CUST-001',
    customer_name: 'Acme Corp',
    mandate_id: 'mandate_abc123',
    payment_method: 'ACH',
    approved_by: 'finance@company.com',
    due_date: '2024-01-15T00:00:00Z',
    idempotency_key: 'unique-key-123'
  })
});
```

### **Step 2: Get Overdue Invoices for Monitoring**

```javascript
// Get overdue invoices from our backend
const response = await fetch('https://your-backend.com/api/v1/integration/overdue-invoices/', {
  headers: {
    'X-API-Key': 'your-api-key'
  }
});
```

### **Step 3: Handle Slack Approvals**

```javascript
// Send approval decision from Slack
const response = await fetch('https://your-backend.com/api/v1/integration/slack/approval/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': 'your-api-key'
  },
  body: JSON.stringify({
    invoice_id: 'INV-2024-001',
    decision: 'approve',
    user_id: 'U1234567890',
    user_name: 'john.doe'
  })
});
```

## 📊 **Key API Endpoints You'll Use**

| Endpoint | Purpose | Method |
|----------|---------|---------|
| `/integration/salesforce/webhook/` | Send collection requests | POST |
| `/integration/overdue-invoices/` | Get overdue invoices | GET |
| `/integration/status/{invoice_id}/` | Get invoice status | GET |
| `/integration/slack/approval/` | Send approval decisions | POST |
| `/integration/webhook/status-update/` | Receive status updates | POST |

## 🔐 **Authentication**

All requests require API key authentication:

```http
X-API-Key: your-api-key-here
```

## 📝 **Environment Configuration**

Add these to your environment:

```bash
COLLECTIONS_BACKEND_URL=https://your-backend.com/api/v1/
COLLECTIONS_API_KEY=your-api-key
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK
```

## 🎯 **Integration Flow**

```
1. Salesforce Agentforce → Detects overdue invoice
2. Salesforce → Calls our backend webhook
3. Our Backend → Processes collection request
4. Our Backend → Sends approval request to Slack
5. Slack → User approves/rejects
6. Slack → Sends decision to our backend
7. Our Backend → Processes payment
8. Our Backend → Updates Salesforce with results
```

## 📚 **Documentation**

- **Complete API Docs**: `INTEGRATION_API_DOCS.md`
- **API Schema**: `https://your-backend.com/api/schema/`
- **Interactive Docs**: `https://your-backend.com/api/docs/`

## 🧪 **Testing**

Set up demo data:

```bash
python manage.py setup_integration_demo
```

This creates:
- Demo A2A agents
- Sample invoices
- Test data for integration

## 🆘 **Support**

- **API Issues**: Check the integration documentation
- **Authentication**: Verify API keys and headers
- **Rate Limits**: 100 requests/minute for general endpoints
- **Error Handling**: All endpoints return consistent error format

## 🎉 **You're Ready to Integrate!**

Your Collections Agent Backend is fully prepared for integration. The core processing engine, APIs, and documentation are all in place. You just need to build the Salesforce Agentforce triggers and Slack app to complete the system!

**Next Steps:**
1. Set up API authentication
2. Test the webhook endpoints
3. Build Salesforce Agentforce integration
4. Build Slack app integration
5. Test end-to-end flow

**Happy Integrating!** 🚀
