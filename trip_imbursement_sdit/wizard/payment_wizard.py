
from odoo import _, api, fields, models


class WizardPaymentWizard(models.TransientModel):
    _name = 'reimbursement.wizard'
    _description = 'Payment Wizard'

    payment_type = fields.Selection([('direct','Direct Payment')], default='direct', required=True)

    def action_do_payment(self):
        context = dict(self._context) or {}
        act_record = self.env['trip.reimbursement'].browse(context['active_ids'])
        if self.payment_type == 'direct':
            act_record.action_create_payment()


