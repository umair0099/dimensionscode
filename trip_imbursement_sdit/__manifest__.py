# -*- coding: utf-8 -*-

{
    'name': 'Trip & Fuel Reimbursement',
    'summary': '''Customizations in the fleet module to the workflow for the reimbursement of trip allowance or fuel allowance by direct payment.''',
    'author': 'Smart Dimensions for Information Technology',
    'website': 'http://sdit.co/',
    'category': 'Custom Fleet',
    'version': '12.0.1',
    'license': 'AGPL-3',
    'depends': [
        'base','fleet','stock'
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/ir_sequence.xml',
        'wizard/payment_wizard_view.xml',
        'views/model_view.xml',
        'report/trip_report.xml',
    ],
    'price': 150.0,
    'currency': 'USD',
    "images": ['static/description/main_banner.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
}
