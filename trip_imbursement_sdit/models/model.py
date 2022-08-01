# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, Warning


class InheritVehicle(models.Model):
    _inherit = 'fleet.vehicle'

    vehicle_type = fields.Selection([('car','Car'), ('van','Van'), ('dyna','Dyna'), ('trailer','Trailer')],default='')
    custom_driver_id = fields.Many2one('hr.employee', string='Driver')


class ReimbursementTrip(models.Model):
    _name = 'trip.reimbursement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Trip Reimbursement'

    @api.depends('trip_lines.trip_amount','trip_lines_fuel.trip_amount')
    def _amount_all(self):
        for order in self:
            amount_total = 0.0
            if order.reimbursement_type == 'trip':
                for line in order.trip_lines:
                    amount_total += line.trip_amount
            if order.reimbursement_type == 'fuel':
                for line in order.trip_lines_fuel:
                    amount_total += line.trip_amount
            order.update({
                'amount_total': amount_total,
            })

    name = fields.Char('Name', strore=True)
    reimbursement_type = fields.Selection([('trip','Trip'),('fuel','Fuel')], default='')
    driver_id = fields.Many2one('hr.employee', string='Driver', store=True, required=True, track_visibility='always')
    manager_id = fields.Many2one(related='driver_id.parent_id')
    department_id = fields.Many2one(related='driver_id.department_id')
    nationality = fields.Many2one(related='driver_id.country_id')
    job_position = fields.Many2one(related='driver_id.job_id')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  default=lambda self: self.env.user.company_id.currency_id.id)
    request_date = fields.Datetime(default=fields.datetime.today(), track_visibility='always', required=True)
    vehicle_id = fields.Many2one('fleet.vehicle', string='Vehicle', required=True, track_visibility='always')
    vehicle_type = fields.Selection([('car','Car'), ('van','Van'), ('dyna','Dyna'), ('trailer','Trailer')],default='', required=True, track_visibility='always')
    license_plate = fields.Char(related='vehicle_id.license_plate')
    chasis_no = fields.Char(related='vehicle_id.vin_sn')
    last_odometer = fields.Float(store=True)
    odometer_unit = fields.Selection(related='vehicle_id.odometer_unit')
    amount_total = fields.Float(store=True, compute='_amount_all')
    opening_millage = fields.Integer(store=True, track_visibility='always')
    closing_millage = fields.Integer(store=True, track_visibility='always')
    difference_millage = fields.Integer(store=True, compute='_compute_millage')
    trip_lines = fields.One2many('trip.lines', 'trip_id')
    trip_lines_fuel = fields.One2many('trip.lines.fuel', 'trip_fuel_id')
    note = fields.Text(store=True)
    trip_attachment = fields.Binary(store=True)
    payment_id = fields.Integer()
    reward_id = fields.Integer()
    is_payment = fields.Boolean(default=False)
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True,
                                 default=lambda self: self.env.user.company_id.id)
    state = fields.Selection([('draft','Draft'),('submitted','Submitted'),('fm_approval','FM Approval'),('hr_approval','HR Approval'),('confirm','Confirm'),('reject','Reject')],default='draft', track_visibility='always')

    @api.onchange('vehicle_type')
    def get_vehicles(self):
        vehicles = []
        if self.vehicle_type:
            vehicle_rec = self.env['fleet.vehicle'].search([('vehicle_type','=',self.vehicle_type)])
            for rec in vehicle_rec:
                vehicles.append(rec.id)
        return {'domain': {'vehicle_id': [('id', 'in', vehicles)]}}

    @api.onchange('vehicle_id')
    def check_vehicles_type(self):
        if self.vehicle_id:
            self.last_odometer = self.vehicle_id.odometer
            if not self.vehicle_type:
                raise ValidationError(_('Select the Vehicle Type'))

    @api.model
    def create(self, vals):
        if vals['reimbursement_type'] == 'trip':
            vals['name'] = self.env['ir.sequence'].next_by_code('seq.trip.reimbursement')
        else:
            vals['name'] = self.env['ir.sequence'].next_by_code('seq.fuel.reimbursement')
        result = super(ReimbursementTrip, self).create(vals)
        return result

    @api.onchange('opening_millage','closing_millage')
    def _compute_millage(self):
        if self.closing_millage:
            if self.closing_millage <= self.opening_millage:
                raise ValidationError(_('Closing Millage should must be greater than opening millage'))
            if self.closing_millage:
                self.difference_millage = self.closing_millage - self.opening_millage

    def update_vehicle_odometer(self):
        if len(self.trip_lines_fuel) > 1:
            self.vehicle_id.odometer = float(self.trip_lines_fuel[-1].closing_millage)
        else:
            self.vehicle_id.odometer = float(self.trip_lines_fuel[0].closing_millage)

    @api.multi
    def action_submit(self):
        if self.reimbursement_type == 'fuel':
            if not self.trip_lines_fuel:
                raise ValidationError(_("Add trip lines before submission."))
            self.update_vehicle_odometer()
        return self.write({'state':'submitted'})

    @api.multi
    def action_fm_approval(self):
        return self.write({'state':'fm_approval'})

    @api.multi
    def action_hr_approval(self):
        return self.write({'state':'hr_approval'})

    @api.multi
    def action_set_to_draft(self):
        return self.write({'state':'draft'})

    @api.multi
    def action_reject(self):
        return self.write({'state':'reject'})

    @api.multi
    def action_confirm(self):
        self.ensure_one()
        return {
            'name': _('Payment Wizard'),
            'res_model': 'reimbursement.wizard',
            'type': 'ir.actions.act_window',
            'view_id': False,
            'view_mode': 'form',
            'view_type': 'form',
            'target': 'new',
        }

    @api.multi
    def action_create_payment(self):
        vendor = self.env['res.partner'].search([('name','=','Fleet Expenses')])
        if not vendor:
            raise ValidationError(_("Please create the vendor with the name 'Fleet Expenses'."))
        if self.amount_total == 0.0:
            raise ValidationError(_("Payment could not suppose to be zero amount."))
        journals = self.env['account.journal'].search([('company_id','=',self.env.user.company_id.id)])
        payment = self.env['account.payment'].create({
                                            'payment_type': 'outbound',
                                            'payment_method_id': 2,
                                            'partner_id': vendor.id,
                                            'partner_type': 'supplier',
                                            'amount':self.amount_total,
                                            'employee': self.driver_id.id,
                                            'journal_id':journals[0].id,
                                            'payment_date': fields.Date.today(),
                                            'communication': self.name,
                                            'state': 'draft',
                                            })
        self.payment_id = payment.id
        self.is_payment = True
        self.state = 'confirm'

    @api.multi
    def action_payment_view(self):
        return {
            'name': _('Payment'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'account.payment',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', '=',self.payment_id)],
        }


class LinesTrip(models.Model):
    _name = 'trip.lines'
    _description = 'Trip Lines'

    trip_id = fields.Many2one('trip.reimbursement')
    trip_date = fields.Datetime(track_visibility='always', required=True)
    trip_type = fields.Selection([('delivery','Sale Delivery'),('transfer','Internal Transfer'),('service','Service')], default='', string='Trip Type')
    delivery_id = fields.Many2one('stock.picking', track_visibility='always')
    trip_distance = fields.Float('Distance(in KM)', required=True, track_visibility='always')
    additional_distance = fields.Float('Additional Dist.(in KM)', track_visibility='always', default=0.0)
    trip_amount = fields.Float('Amount', compute='_compute_trip_amount', store=True)
    from_location = fields.Many2one('stock.location', store=True, string='Trip From(Origin)')
    from_address = fields.Char(store=True)
    to_address = fields.Char(store=True)
    shipping_partner_id = fields.Many2one('res.partner', store=True)
    trip_line_attachment = fields.Binary(store=True)
    comments = fields.Char(store=True)
    invoice_no = fields.Char(related='delivery_id.origin', string='Invoice No.')

    @api.onchange('delivery_id')
    def get_drivers_picking(self):
        deliveries = []
        address = []
        if not self.trip_id.driver_id:
            raise ValidationError(_('Please select driver'))
        pickings = self.env['stock.picking'].search([('driver_name','=',self.trip_id.driver_id.id),('state','=','done')])
        for rec in pickings:
            deliveries.append(rec.id)
        if self.delivery_id:
            for rec in self:
                if rec.trip_type == 'delivery':
                    address_shipping = self.env['res.partner'].search(
                        [('parent_id', '=', self.delivery_id.partner_id.id), ('type', '=', 'delivery')])
                    if not address_shipping:
                        raise ValidationError(_('Define shipping address on %s') % (self.delivery_id.partner_id.name))
                    for items in address_shipping:
                        address.append(items.id)
            self.from_location = self.delivery_id.location_id.id
            self.from_address = self.delivery_id.location_id.address_stock
            if not self.delivery_id.location_id.address_stock:
                raise ValidationError(_('Define address on %s') % (self.delivery_id.location_id.complete_name))
        if self.delivery_id.picking_type_id.code == 'internal':
            if not self.delivery_id.location_dest_id.address_stock:
                raise ValidationError(_('Define address on %s')%(self.delivery_id.location_dest_id.complete_name))
            self.to_address = self.delivery_id.location_dest_id.address_stock
        return {'domain': {'delivery_id': [('id', 'in', deliveries)],'shipping_partner_id': [('id', 'in', address)]}}

    @api.onchange('shipping_partner_id')
    def get_shipping_address(self):
        for rec in self:
            if rec.shipping_partner_id:
                if not (rec.shipping_partner_id.state_id and rec.shipping_partner_id.zip and rec.shipping_partner_id.city):
                    raise ValidationError(_('Define complete shipping address detail on %s') % (rec.delivery_id.partner_id.name))
                rec.to_address = rec.shipping_partner_id.street + ',' + rec.shipping_partner_id.city + ',' + rec.shipping_partner_id.state_id.name + ',' + rec.shipping_partner_id.zip + ',' + rec.shipping_partner_id.country_id.name
                rec.trip_distance = rec.shipping_partner_id.distance_km

    @api.depends('trip_distance','additional_distance')
    def _compute_trip_amount(self):
        for rec in self:
            if rec.trip_distance:
                total_distance = rec.trip_distance + rec.additional_distance
                print(total_distance)
                rate_lines = self.env['trip.rate.lines'].search([('vehicle_type','=',rec.trip_id.vehicle_type),('trip_rate_id.company_id','=',rec.trip_id.company_id.id)])
                if not rate_lines:
                    raise ValidationError(_('Trip Configuration may not be defined'))
                for lines in rate_lines:
                    if total_distance <= lines.km_value:
                        if lines.km_range == 'under' and lines.type_rate == 'fixed':
                            rec.trip_amount = lines.fixed_amount
                        elif lines.km_range == 'under' and lines.type_rate == 'percentage':
                            rec.trip_amount = (lines.fixed_percentage * total_distance) / 100
                    elif total_distance >= lines.km_value:
                        if lines.km_range == 'over' and lines.type_rate == 'percentage':
                            rec.trip_amount = (lines.fixed_percentage * total_distance) / 100
                        elif lines.km_range == 'over' and lines.type_rate == 'fixed':
                            rec.trip_amount = lines.fixed_amount


class LinesTripFuel(models.Model):
    _name = 'trip.lines.fuel'
    _description = 'Fuel Lines'

    trip_fuel_id = fields.Many2one('trip.reimbursement')
    trip_date = fields.Datetime(track_visibility='always', required=True)
    trip_type = fields.Selection([('delivery','Sale Delivery'),('transfer','Internal Transfer'),('service','Service')], default='', string='Trip Type')
    delivery_id = fields.Many2one('stock.picking', track_visibility='always')
    trip_amount = fields.Float('Amount', compute='_compute_trip_amount', store=True)
    opening_millage = fields.Integer(store=True, track_visibility='always')
    closing_millage = fields.Integer(store=True, track_visibility='always')
    difference_millage = fields.Integer(store=True, compute='_compute_millage')
    from_location = fields.Many2one('stock.location', store=True, string='Trip From(Origin)')
    from_address = fields.Char(store=True)
    to_address = fields.Char(store=True)
    shipping_partner_id = fields.Many2one('res.partner', store=True)
    trip_line_attachment = fields.Binary(store=True)
    comments = fields.Char(store=True)
    invoice_no = fields.Char(related='delivery_id.origin', string='Invoice No.')

    @api.onchange('delivery_id')
    def get_drivers_picking(self):
        deliveries = []
        address = []
        if not self.trip_fuel_id.driver_id:
            raise ValidationError(_('Please select driver'))
        pickings = self.env['stock.picking'].search([('driver_name','=',self.trip_fuel_id.driver_id.id),('state','=','done')])
        for rec in pickings:
            deliveries.append(rec.id)
        if self.delivery_id:
            for rec in self:
                if rec.trip_type == 'delivery':
                    address_shipping = self.env['res.partner'].search(
                        [('parent_id', '=', self.delivery_id.partner_id.id), ('type', '=', 'delivery')])
                    if not address_shipping:
                        raise ValidationError(_('Define shipping address on %s') % (self.delivery_id.partner_id.name))
                    for items in address_shipping:
                        address.append(items.id)
            self.from_location = self.delivery_id.location_id.id
            self.from_address = self.delivery_id.location_id.address_stock
            if not self.delivery_id.location_id.address_stock:
                raise ValidationError(_('Define address on %s') % (self.delivery_id.location_id.complete_name))
        if self.delivery_id.picking_type_id.code == 'internal':
            if not self.delivery_id.location_dest_id.address_stock:
                raise ValidationError(_('Define address on %s')%(self.delivery_id.location_dest_id.complete_name))
            self.to_address = self.delivery_id.location_dest_id.address_stock
        return {'domain': {'delivery_id': [('id', 'in', deliveries)],'shipping_partner_id': [('id', 'in', address)]}}

    @api.onchange('shipping_partner_id')
    def get_shipping_address(self):
        for rec in self:
            if rec.shipping_partner_id:
                if not (rec.shipping_partner_id.state_id and rec.shipping_partner_id.zip and rec.shipping_partner_id.city):
                    raise ValidationError(_('Define complete shipping address detail on %s') % (rec.delivery_id.partner_id.name))
                rec.to_address = rec.shipping_partner_id.street + ',' + rec.shipping_partner_id.city + ',' + rec.shipping_partner_id.state_id.name + ',' + rec.shipping_partner_id.zip + ',' + rec.shipping_partner_id.country_id.name

    @api.onchange('opening_millage','closing_millage')
    def _compute_millage(self):
        for rec in self:
            if rec.closing_millage:
                if rec.closing_millage <= rec.opening_millage:
                    raise ValidationError(_('Closing Millage should must be greater than opening millage'))
                if rec.closing_millage:
                    rec.difference_millage = rec.closing_millage - rec.opening_millage

    @api.depends('difference_millage')
    def _compute_trip_amount(self):
        for rec in self:
            if rec.difference_millage:
                rate_lines = self.env['fuel.rate.lines'].search([('vehicle_type','=',rec.trip_fuel_id.vehicle_type),('fuel_rate_id.company_id','=',rec.trip_fuel_id.company_id.id)])
                if not rate_lines:
                    raise ValidationError(_('Fuel Configuration may not be defined'))
                for lines in rate_lines:
                    if rec.difference_millage <= lines.km_value:
                        if lines.km_range == 'under' and lines.type_rate == 'fixed':
                            rec.trip_amount = ((rec.difference_millage/lines.km_per_liter)*lines.fixed_amount)
                        elif lines.km_range == 'under' and lines.type_rate == 'percentage':
                            rec.trip_amount = ((rec.difference_millage / lines.km_per_liter) * lines.fixed_amount)
                    elif rec.difference_millage >= lines.km_value:
                        if lines.km_range == 'over' and lines.type_rate == 'percentage':
                            rec.trip_amount = ((rec.difference_millage / lines.km_per_liter) * lines.fixed_amount)
                        elif lines.km_range == 'over' and lines.type_rate == 'fixed':
                            rec.trip_amount = ((rec.difference_millage/lines.km_per_liter)*lines.fixed_amount)


class TripConfiguration(models.Model):
    _name = 'trip.configuration'
    _description = 'Trip Configuration'

    @api.model
    def create(self, vals):
        self.env.cr.execute("select count(*) from trip_configuration where company_id = %s" % vals['company_id'])
        records = self.env.cr.fetchall()
        if records[0][0] > 0:
            raise Warning(_('Please edit the settings, creation not allowed.'))
        return super(TripConfiguration, self).create(vals)

    name = fields.Char()
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True,
                                 default=lambda self: self.env.user.company_id.id)
    trip_config_ids = fields.One2many('trip.rate.lines', 'trip_rate_id')
    fuel_config_ids = fields.One2many('fuel.rate.lines', 'fuel_rate_id')


class TripRate(models.Model):
    _name = 'trip.rate.lines'
    _description = 'Trip Rate'

    trip_rate_id = fields.Many2one('trip.configuration')
    vehicle_type = fields.Selection([('car', 'Car'), ('van', 'Van'), ('dyna', 'Dyna'), ('trailer', 'Trailer')],
                                    default='')
    km_range = fields.Selection([('under', 'Under'), ('over', 'Over')], default='')
    km_value = fields.Float(store=True)
    type_rate = fields.Selection([('fixed','Fixed'),('percentage','Percentage')], default='')
    fixed_amount = fields.Float(store=True)
    fixed_percentage = fields.Float(store=True)
    comment = fields.Char(store=True)


class FuelRate(models.Model):
    _name = 'fuel.rate.lines'
    _description = 'Fuel Rate'

    fuel_rate_id = fields.Many2one('trip.configuration')
    vehicle_type = fields.Selection([('car', 'Car'), ('van', 'Van'), ('dyna', 'Dyna'), ('trailer', 'Trailer')],
                                    default='')
    km_range = fields.Selection([('under', 'Under'), ('over', 'Over')], default='')
    km_value = fields.Float(store=True)
    type_rate = fields.Selection([('fixed','Fixed'),('percentage','Percentage')], default='')
    fixed_amount = fields.Float(store=True)
    fixed_percentage = fields.Float(store=True)
    km_per_liter = fields.Float(store=True)
    comment = fields.Char(store=True)


class InheritLocationStock(models.Model):
    _inherit = 'stock.location'

    address_stock = fields.Char('Address')


class ResInheritPartner(models.Model):
    _inherit = 'res.partner'

    warehouse_loc_id = fields.Many2one('stock.location')
    distance_km = fields.Float('Distance(in km)')