from rest_framework import serializers
from core.models import Merchant, Payout, Transaction

class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = ['id', 'amount_paise', 'bank_account_id', 'state', 'created_at', 'updated_at', 'merchant']

class PayoutRequestSerializer(serializers.Serializer):
    amount_paise = serializers.IntegerField(min_value=1)
    bank_account_id = serializers.CharField(max_length=255)

class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['id', 'amount_paise', 'txn_type', 'created_at']

class MerchantDashboardSerializer(serializers.ModelSerializer):
    available_balance = serializers.SerializerMethodField()
    held_balance = serializers.SerializerMethodField()
    recent_transactions = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        fields = ['id', 'name', 'available_balance', 'held_balance', 'recent_transactions']

    def get_available_balance(self, obj):
        return obj.balance_paise

    def get_held_balance(self, obj):
        # With the new 'Invoice'/'Payment Request' semantics, requesting a payout
        # does not hold funds.
        return 0

    def get_recent_transactions(self, obj):
        txns = Transaction.objects.filter(merchant=obj).order_by('-created_at')[:10]
        return TransactionSerializer(txns, many=True).data
