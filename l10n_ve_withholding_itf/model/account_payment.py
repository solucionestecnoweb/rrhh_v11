# coding: utf-8
###########################################################################

from odoo import fields, models, api,_
from odoo.exceptions import UserError


class account_payment(models.Model):
    _name = 'account.payment'
    _inherit = 'account.payment'

    move_itf_id = fields.Many2one('account.move', 'Asiento contable')


    @api.multi
    def post(self):
        """Genera la retencion del 2% después que realiza el pago"""
        res = super(account_payment, self).post()

        for pago in self:
            idem = pago.check_partner()
            itf_bool = pago._get_company_itf()
            type_bool = pago.check_payment_type()

            if res and idem and itf_bool and type_bool:
                pago.register_account_move_payment()
        return res

    def register_account_move_payment(self):
        '''Este método realiza el asiento contable de la comisión según el porcentaje que indica la compañia'''

        name = self.get_name()
        #self.env['ir.sequence'].with_context(ir_sequence_date=self.date_advance).next_by_code(sequence_code)
        vals = {
            'name': name,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'line_ids': False,
            'state': 'posted',
        }
        move_obj = self.env['account.move']
        move_id = move_obj.create(vals)
        porcentage_itf= self._get_company().wh_porcentage
        #calculo del 2% del pago
        amount_itf = round(float(self.amount) * float((porcentage_itf / 100.00)),2)
        #amount_itf = self.compute_itf()

        self.move_advance_ = {
            'account_id': self.journal_id.default_debit_account_id.id,
            'company_id': self._get_company().id,
            'currency_id': self.currency_id.id,
            'date_maturity': False,
            'ref': "Comisión del %s %% del pago %s por comisión" % (porcentage_itf,self.name),
            'date': self.payment_date,
            'partner_id': self.partner_id.id,
            'move_id': move_id.id,
            'name': "Comisión del %s %% del pago %s por comisión" % (porcentage_itf, self.name),
            'journal_id': self.journal_id.id,
            'credit': float(amount_itf),
            'debit': 0.0,
            'amount_currency': 0.0,
        }

        asiento = self.move_advance_
        move_line_obj = self.env['account.move.line']
        move_line_id1 = move_line_obj.create(asiento)

        asiento['account_id'] = self._get_company().account_wh_itf_id.id
        asiento['credit'] = 0.0
        asiento['debit'] = float(amount_itf)

        move_line_id2 = move_line_obj.create(asiento)

        if move_line_id1 and move_line_id2:
            res = {'move_itf_id': asiento['move_id']}
            self.write(res)
        return True

    @api.model
    def _get_company(self):
        '''Método que busca el id de la compañia'''
        company_id = self.env['res.users'].browse(self.env.uid).company_id
        return company_id

    def _get_company_itf(self):
        '''Método que retorna verdadero si la compañia debe retener el impuesto ITF'''
        company_id = self._get_company()
        if company_id.calculate_wh_itf:
            return True
        return False

    @api.model
    def check_payment_type(self):
        '''metodo que chequea que el tipo de pago si pertenece al tipo outbound'''
        type_bool = False
        for pago in self:
            type_payment = pago.payment_type
            if type_payment == 'outbound':
                type_bool = True
        return type_bool


    @api.model
    def check_partner(self):
        '''metodo que chequea el rif de la empresa y la compañia si son diferentes
        retorna True y si son iguales retorna False'''
        idem = False
        company_id = self._get_company()
        for pago in self:
            if pago.partner_id.vat != company_id.partner_id.vat:
                idem = True
                return idem
        return idem


    def get_name(self):
        '''metodo que crea el name del asiento contable si la secuencia no esta creada crea una con el
        nombre: 'l10n_account_withholding_itf'''

        self.ensure_one()
        SEQUENCE_CODE = 'l10n_account_withholding_itf'
        company_id = self._get_company()
        IrSequence = self.env['ir.sequence'].with_context(force_company=company_id.id)
        name = IrSequence.next_by_code(SEQUENCE_CODE)

        # if a sequence does not yet exist for this company create one
        if not name:
            IrSequence.sudo().create({
                'prefix': 'WITF',
                'name': 'Localización Venezolana impuesto ITF %s' % company_id.id,
                'code': SEQUENCE_CODE,
                'implementation': 'no_gap',
                'padding': 8,
                'number_increment': 1,
                'company_id': company_id.id,
            })
            name = IrSequence.next_by_code(SEQUENCE_CODE)
        return name

    @api.multi
    def cancel(self):
        """Calcela el movimiento contable si se cancela el pago de las facturas"""
        res = super(account_payment, self).cancel()
        date = fields.Datetime.now()
        for pago in self:
            if pago.state == 'cancelled':
                for move in pago.move_itf_id:
                    move_reverse = move.reverse_moves(date, self.journal_id)
                    if len(move_reverse) == 0:
                        raise UserError(_('No se reversaron los asientos asociados'))
        return res

class account_move(models.Model):
    _inherit = 'account.move'

    @api.multi
    def assert_balanced(self):
        if not self.ids:
            return True
        mlo = self.env['account.move.line'].search([('move_id', '=',self.ids[0])])
        if not mlo.reconcile:
            super(account_move, self).assert_balanced(fields)
        return True