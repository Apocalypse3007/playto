from rest_framework import status, views
from rest_framework.response import Response
from django.db import transaction, IntegrityError
from django.utils import timezone
from datetime import timedelta

from core.models import Merchant, IdempotencyKey, Payout, Transaction
from core.services import request_payout, InsufficientFundsError
from core.tasks import process_payout
from .serializers import PayoutRequestSerializer, PayoutSerializer, MerchantDashboardSerializer

class MerchantCreateView(views.APIView):
    def post(self, request):
        name = request.data.get('name')
        if not name:
            return Response({'error': 'Name is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                merchant = Merchant.objects.create(name=name)
                # Seed with 10,000 INR
                Transaction.objects.create(
                    merchant=merchant,
                    amount_paise=1000000,
                    txn_type=Transaction.Type.CREDIT
                )
            return Response({'id': merchant.id, 'name': merchant.name}, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MerchantDashboardView(views.APIView):
    def get(self, request, merchant_id):
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
            
        serializer = MerchantDashboardSerializer(merchant)
        
        # Also include payout history
        from django.db.models import Q
        payouts = Payout.objects.filter(
            Q(merchant=merchant) | Q(bank_account_id=str(merchant.id))
        ).order_by('-created_at')[:20]
        payouts_data = PayoutSerializer(payouts, many=True).data
        
        data = serializer.data
        data['payouts'] = payouts_data
        return Response(data)

class PayoutRequestView(views.APIView):
    def post(self, request, merchant_id):
        idemp_key = request.headers.get('Idempotency-Key')
        if not idemp_key:
            return Response({"error": "Idempotency-Key header is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except Merchant.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        # Idempotency check with locking to prevent race condition when 2nd arrives while 1st is in-flight
        try:
            with transaction.atomic():
                idem_record, created = IdempotencyKey.objects.select_for_update().get_or_create(
                    key=idemp_key,
                    merchant=merchant
                )
                
                # Check expiration 24h
                if timezone.now() - idem_record.created_at > timedelta(hours=24):
                    return Response({"error": "Idempotency key expired"}, status=status.HTTP_400_BAD_REQUEST)
                
                if not created:
                    # It already existed.
                    if idem_record.response_body is not None:
                        # Request #1 already finished, return exact same response
                        return Response(idem_record.response_body, status=idem_record.response_status)
                    else:
                        # Request #1 is STILL IN FLIGHT. The select_for_update() actually makes Request #2 block
                        # until Request #1's transaction finishes. However, if they were truly concurrent, 
                        # one would get create=True and lock, the other would block on get_or_create then see create=False.
                        # Wait, if get_or_create blocks and then resumes, response_body might be there now!
                        # BUT wait, the response saving happens *outside* this atomic block (at the end of the view).
                        # So if we are here and response_body is None, it means the request is currently in-progress.
                        return Response({"error": "Request already in progress"}, status=status.HTTP_409_CONFLICT)
                
                # If we get here, `created` is True, meaning we're the first one to acquire it.
                # The idempotent record is now locked and committed. Wait, we should commit this first so others can see it!
                # Actually, if we commit here, others will see it as in-flight.
        except IntegrityError:
            return Response({"error": "Idempotency key collision"}, status=status.HTTP_409_CONFLICT)
            
        # Parse payload
        serializer = PayoutRequestSerializer(data=request.data)
        if not serializer.is_valid():
            self._save_idempotency_state(idemp_key, merchant, serializer.errors, status.HTTP_400_BAD_REQUEST)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        amount_paise = serializer.validated_data['amount_paise']
        bank_account_id = serializer.validated_data['bank_account_id']
        
        # Core Ledger Logic
        try:
            # We don't put this in the idempotency transaction block because we don't want to lock the 
            # idempotency row for the duration of the payout logic. Payout logic locks the merchant balance row!
            payout = request_payout(
                merchant_id=merchant.id,
                amount_paise=amount_paise,
                bank_account_id=bank_account_id,
                idempotency_key=idemp_key
            )
        except InsufficientFundsError as e:
            err_resp = {"error": str(e)}
            self._save_idempotency_state(idemp_key, merchant, err_resp, status.HTTP_400_BAD_REQUEST)
            return Response(err_resp, status=status.HTTP_400_BAD_REQUEST)
            
        # Success path
        resp_data = PayoutSerializer(payout).data
        
        # Save idempotency state
        self._save_idempotency_state(idemp_key, merchant, resp_data, status.HTTP_201_CREATED, payout_id=payout.id)
        
        # Fire off celery task
        process_payout.apply_async((str(payout.id),))
        
        return Response(resp_data, status=status.HTTP_201_CREATED)
        
    def _save_idempotency_state(self, key, merchant, response_body, response_status, payout_id=None):
        idem_record = IdempotencyKey.objects.get(key=key, merchant=merchant)
        
        import json
        from django.core.serializers.json import DjangoJSONEncoder
        
        # Serialize and deserialize using Django's encoder to convert UUIDs and Datetimes to strings
        safe_response_body = json.loads(json.dumps(response_body, cls=DjangoJSONEncoder))
        
        idem_record.response_body = safe_response_body
        idem_record.response_status = response_status
        idem_record.payout_id = payout_id
        idem_record.save()

class SettlePayoutView(views.APIView):
    def post(self, request, payout_id):
        try:
            payout = Payout.objects.get(id=payout_id)
        except Payout.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
            
        from core.services import transition_payout_state
        if payout.state == Payout.State.PENDING:
            transition_payout_state(payout.id, Payout.State.PROCESSING)
            transition_payout_state(payout.id, Payout.State.COMPLETED)
        elif payout.state == Payout.State.PROCESSING:
            transition_payout_state(payout.id, Payout.State.COMPLETED)
            
        return Response({"status": "settled"})
