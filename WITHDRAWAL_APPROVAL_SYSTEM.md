# Withdrawal Approval System

## Overview
The withdrawal system has been updated to require owner approval for all withdrawal requests. This provides better control and prevents unauthorized withdrawals.

## How It Works

### User Perspective

**Command Usage:**
```
!withdraw              # Request withdrawal of full balance
!withdraw <amount>     # Request withdrawal of specific amount
```

**Examples:**
```
!withdraw              # Withdraw all available balance
!withdraw 50m          # Withdraw 50 million
!withdraw 100k         # Withdraw 100 thousand
!withdraw 1b           # Withdraw 1 billion
```

**Process:**
1. User runs the withdrawal command
2. Bot validates:
   - User has a positive balance
   - Gambling requirement is met (gambled >= required_gamble)
   - Amount doesn't exceed balance (if specified)
3. Bot sends an embed showing:
   - User making the request
   - Amount requested
   - Current balance
   - Remaining balance after withdrawal
4. User waits for owner to approve or decline
5. User receives notification when request is processed

### Owner Perspective

**Approval Process:**
1. Bot sends withdrawal request embed with two buttons:
   - ✅ **Confirm Withdrawal** (Green)
   - ❌ **Decline Withdrawal** (Red)
2. Owner clicks appropriate button
3. Bot processes the action immediately

**On Confirmation:**
- Withdrawal is processed
- User's balance is updated
- User is notified: "✅ @user Your withdrawal of X$ has been approved!"
- Logged to withdrawal channel: "💸 user withdrew X$ SAB currency. Approved by owner."
- Embed updates to show approval status

**On Decline:**
- No balance changes
- User is notified: "❌ @user Your withdrawal request has been declined."
- Embed updates to show decline status

## Features

### Security
- **Owner-Only Buttons**: Only users with IDs in `OWNER_IDS` can click approve/decline buttons
- **Timeout Protection**: Requests expire after 5 minutes
- **Input Validation**: All amounts are validated before creating request
- **Balance Verification**: Cannot withdraw more than available balance

### User Experience
- **Flexible Amounts**: Can withdraw full balance or specify partial amount
- **Clear Feedback**: Embed shows all relevant information
- **Notifications**: User is always notified of the outcome
- **Visual Status**: Buttons are disabled after action to prevent duplicate clicks

### Logging
- All approved withdrawals are logged to `WITHDRAWAL_LOG_CHANNEL`
- Log includes:
  - User who withdrew
  - Amount withdrawn
  - Owner who approved
  - Timestamp

## Code Implementation

### WithdrawalConfirmView Class
```python
class WithdrawalConfirmView(View):
    def __init__(self, user, amount, channel):
        super().__init__(timeout=300)  # 5 minute timeout
        self.user = user
        self.amount = amount
        self.channel = channel
```

**Buttons:**
1. `confirm_withdrawal` - Processes withdrawal and notifies user
2. `decline_withdrawal` - Declines request and notifies user

**Timeout Handler:**
- `on_timeout()` - Handles expired requests (disables buttons)

### Updated !withdraw Command
```python
@bot.command(name="withdraw")
async def withdraw(ctx, amount: str = None):
    # Validates requirements
    # Parses amount (full or partial)
    # Creates embed with details
    # Sends with WithdrawalConfirmView
```

## Examples

### Example 1: Full Balance Withdrawal
```
User: !withdraw
Bot: [Sends embed]
      💸 Withdrawal Request
      User: @johndoe
      Amount: 150,000,000$
      Current Balance: 150,000,000$
      Remaining After: 0$
      [✅ Confirm] [❌ Decline]

Owner: [Clicks ✅ Confirm]
Bot: ✅ Withdrawal Approved
     @johndoe withdrew 150,000,000$ SAB currency.
     Approved By: @owner
     
Bot: @johndoe Your withdrawal of 150,000,000$ has been approved!
```

### Example 2: Partial Withdrawal
```
User: !withdraw 50m
Bot: [Sends embed]
      💸 Withdrawal Request
      User: @johndoe
      Amount: 50,000,000$
      Current Balance: 150,000,000$
      Remaining After: 100,000,000$
      [✅ Confirm] [❌ Decline]

Owner: [Clicks ❌ Decline]
Bot: ❌ Withdrawal Declined
     Withdrawal request from @johndoe has been declined.
     Declined By: @owner
     
Bot: @johndoe Your withdrawal request has been declined.
```

### Example 3: Timeout
```
User: !withdraw 25m
Bot: [Sends embed with buttons]
[5 minutes pass with no owner action]
Bot: [Disables buttons]
     ⏱️ Withdrawal Request Expired
     Withdrawal request from @johndoe has timed out.
```

## Error Handling

### User Errors
- **No balance**: "❌ You must make a deposit in order to withdraw."
- **Gambling requirement not met**: "❌ You must gamble X$ before withdrawing."
- **Invalid amount format**: "❌ Invalid amount format! Use k, m, or b (e.g., 10m, 5k)."
- **Amount exceeds balance**: "❌ You cannot withdraw more than your balance (X$)."

### Owner Errors
- **Non-owner tries to click**: "❌ Only owners can confirm/decline withdrawals."

### System Errors
- **Processing error**: "❌ Error processing withdrawal: [error details]"
- **Request error**: "❌ Error processing withdrawal request: [error details]"

## Benefits

### For Owners
✅ Full control over all withdrawals
✅ Review each request before approval
✅ Prevent fraudulent withdrawals
✅ Track who approved what in logs
✅ Can decline suspicious requests

### For Users
✅ Clear process and feedback
✅ Flexible withdrawal amounts
✅ Know exactly what's happening
✅ Can withdraw partial amounts
✅ Fair and transparent system

### For the Bot
✅ Maintains data integrity
✅ Prevents race conditions
✅ Proper error handling
✅ Comprehensive logging
✅ Secure by design
