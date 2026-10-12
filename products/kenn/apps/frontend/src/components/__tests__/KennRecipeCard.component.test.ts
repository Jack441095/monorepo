// @vitest-environment happy-dom
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import KennRecipeCard from '../KennRecipeCard.vue'
import type { KennActionProposal } from '../../api/kenn'

// Built from what handle_command actually returned for "turn the hats down 3 dB and the kick up 2 dB" on
// FakeLiveBackend on 2026-09-30, so this is the shape the card has to render rather than an idealised one.
const recipe: KennActionProposal = {
  schema: 'kenn.ableton_recipe_proposal.v1',
  action: 'recipe',
  operation: 'recipe',
  target: 'ableton_recipe',
  confirmation_token: 'recipe-7cdd85d0',
  steps: [
    {
      action_id: 'action-69422e77',
      action: 'set_volume',
      operation: 'set_volume',
      track_index: 2,
      track_name: 'Hi-Hats',
      before: 0.5,
      after: 0.472,
      before_db: -14,
      after_db: -17,
      unit: 'normalized',
      requires_confirmation: true,
    },
    {
      action_id: 'action-2b81c4aa',
      action: 'set_volume',
      operation: 'set_volume',
      track_index: 0,
      track_name: 'Kick',
      before: 0.5,
      after: 0.524,
      before_db: -14,
      after_db: -12,
      unit: 'normalized',
      requires_confirmation: true,
    },
  ],
}

describe('KennRecipeCard', () => {
  it('names the track on every step', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe } })
    expect(wrapper.text()).toContain('Hi-Hats')
    expect(wrapper.text()).toContain('Kick')
  })

  it('keeps the guarded EQ target and displayed values visible before and after Apply', () => {
    // Compound EQ and setup return recipe children, whose raw values are not their displayed units.
    const eq: KennActionProposal = {
      ...recipe,
      steps: [
        { action: 'set_device_parameter', track_name: 'Bus', device_name: 'EQ Eight', parameter: '2 Frequency A',
          target_label: 'Bus / EQ Eight / 2 Frequency A',
          target_address: { kind: 'track', index: 0, device_path: [1] },
          before: 0.2, after: 0.4, before_display: '250 Hz', after_display: '1000 Hz', unit: 'hz' },
        { action: 'set_device_parameter', track_name: 'Bus', device_name: 'EQ Eight', parameter: '2 Gain A',
          target_label: 'Bus / EQ Eight / 2 Gain A',
          target_address: { kind: 'track', index: 0, device_path: [1] },
          before: 0.5, after: 0.6, before_display: '0 dB', after_display: '3 dB', unit: 'db' },
      ],
    }
    for (const cardStatus of ['pending', 'applied'] as const) {
      const rows = mount(KennRecipeCard, { props: { proposal: eq, cardStatus } }).findAll('li')
      expect(rows[0].text()).toContain('Bus / EQ Eight / 2 Frequency A')
      expect(rows[0].text()).toContain('Track 1, device 2')
      expect(rows[0].text()).toContain('250 Hz → 1000 Hz')
      expect(rows[1].text()).toContain('Bus / EQ Eight / 2 Gain A')
      expect(rows[1].text()).toContain('Track 1, device 2')
      expect(rows[1].text()).toContain('0 dB → 3 dB')
      expect(rows.map(row => row.text()).join(' ')).not.toContain('value to be confirmed')
    }
  })

  it('distinguishes duplicate devices and rack chains with the same observed names', () => {
    // Live labels contain names only; the address supplies the position that disambiguates each target.
    const duplicate: KennActionProposal = { ...recipe, steps: [0, 1].map(chain => ({
      action: 'set_device_parameter', target_label: 'Return A / Rack / Bass / EQ Eight / Gain',
      target_address: { kind: 'return', index: 0, device_path: [1, chain, 0] },
      parameter: 'Gain', before: 0.5, after: 0.6,
    })) }
    const rows = mount(KennRecipeCard, { props: { proposal: duplicate } }).findAll('li')
    expect(rows[0].text()).toContain('Return 1, device 2 / chain 1 / device 1')
    expect(rows[1].text()).toContain('Return 1, device 2 / chain 2 / device 1')
  })

  it('distinguishes duplicate parameter names on the same device', () => {
    // Max for Live and plug-ins can expose two controls with the same name on one device.
    const duplicate: KennActionProposal = { ...recipe, steps: [2, 7].map(parameter_index => ({
      action: 'set_device_parameter', target_label: 'Master / Compressor / Mode',
      target_address: { kind: 'master', index: 0, device_path: [1] },
      parameter_index, parameter: 'Mode', before: 0, after: 1,
    })) }
    const rows = mount(KennRecipeCard, { props: { proposal: duplicate } }).findAll('li')
    expect(rows[0].text()).toContain('Master, device 2 / parameter 3')
    expect(rows[1].text()).toContain('Master, device 2 / parameter 8')
  })

  it('labels device values as raw when the proposal has no mapped displays', () => {
    // A requested unit is not proof that raw 0.25 means 0.25 dB.
    const raw: KennActionProposal = { ...recipe, steps: [
      { action: 'set_device_parameter', track_name: 'Vocal', device_name: 'Compressor', parameter: 'Output',
        before: 0, after: 0.25, unit: 'db' },
    ] }
    const text = mount(KennRecipeCard, { props: { proposal: raw } }).text()
    expect(text).toContain('Vocal / Compressor')
    expect(text).toContain('Output')
    expect(text).toContain('0 raw → 0.25 raw')
    expect(text).not.toContain('0.25 dB')
  })

  it('shows retained sparse choice labels for the plan and its inverse before and after Apply', () => {
    // The recipe card discarded the same Peak/RMS labels that the single-control card already displayed.
    const choice = { action: 'set_device_parameter', parameter: 'Mode',
      target_label: 'Bus / Compressor / Mode', before: 2, after: 7,
      before_label: 'Peak', after_label: 'RMS', before_display: '2 raw', after_display: '7 raw' }
    const inverse = { ...choice, before: 7, after: 2, before_label: 'RMS', after_label: 'Peak',
      before_display: '7 raw', after_display: '2 raw' }
    for (const cardStatus of ['pending', 'applied'] as const) {
      for (const [step, expected] of [[choice, 'Peak → RMS'], [inverse, 'RMS → Peak']] as const) {
        const text = mount(KennRecipeCard, { props: { proposal: { ...recipe, steps: [step] }, cardStatus } }).text()
        expect(text).toContain(expected)
        expect(text).not.toContain('raw →')
      }
    }
  })

  it('never renders the bare "Track " label the single-action card produced', () => {
    // This is the defect it exists for: a recipe carries no track_name of its own, so the old card printed
    // `track_name || "Track " + (track_index != null ? ... : '')` and got an empty track.
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe } })
    expect(wrapper.text()).not.toMatch(/Track\s*$|Track\s{2,}/m)
    expect(wrapper.text()).not.toContain('Track 1')
  })

  it('shows how many changes there are', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe } })
    expect(wrapper.text()).toContain('2 changes')
    expect(wrapper.findAll('li')).toHaveLength(2)
  })

  it('says nothing has changed yet before Apply', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'pending' } })
    expect(wrapper.text()).toContain('Nothing has changed yet')
  })

  it('applies the whole plan in one action, because a step cannot be applied on its own', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'requires_confirmation' } })
    const apply = wrapper.find('.kenn-recipe-card__btn--apply')
    expect(apply.exists()).toBe(true)
    expect(apply.text()).toContain('Apply all 2')
    apply.trigger('click')
    expect(wrapper.emitted('apply')).toHaveLength(1)
  })

  it('offers no Apply once the plan is applied', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'applied' } })
    expect(wrapper.find('.kenn-recipe-card__btn--apply').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Nothing has changed yet')
  })

  it('waits with disabled dismissal and no Apply until token revocation finishes', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'dismissing' } })
    expect(wrapper.text()).toContain('Dismissing...')
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.kenn-recipe-card__btn--apply').exists()).toBe(false)
    expect(wrapper.find('.kenn-recipe-card__btn--reject').exists()).toBe(false)
  })

  it('falls back to a track index when a step has no name', () => {
    const unnamed: KennActionProposal = {
      ...recipe,
      steps: [{ action: 'set_mute', operation: 'set_mute', track_index: 3 }],
    }
    expect(mount(KennRecipeCard, { props: { proposal: unnamed } }).text()).toContain('Track 4')
  })

  it('says the value is unconfirmed rather than showing a blank transition', () => {
    const noDb: KennActionProposal = {
      ...recipe,
      steps: [{ action: 'set_mute', operation: 'set_mute', track_name: 'Kick' }],
    }
    expect(mount(KennRecipeCard, { props: { proposal: noDb } }).text()).toContain('value to be confirmed')
  })

  it('renders a label rather than a raw action name', () => {
    expect(mount(KennRecipeCard, { props: { proposal: recipe } }).text()).toContain('VOLUME')
    expect(mount(KennRecipeCard, { props: { proposal: recipe } }).text()).not.toContain('set_volume')
  })

  it('surfaces an error rather than swallowing it', () => {
    const wrapper = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'error', errorMessage: 'boom' } })
    expect(wrapper.text()).toContain('boom')
  })

  it('offers no Undo on a plan that was itself an undo, because undoing it would redo the change', () => {
    // 9 Oct 2026: "Undo the plan" on an applied undo card called propose_undo on the undo's receipt and put the
    // producer's change straight back.
    const receipt = { receipt_id: 'receipt-undo', action: 'recipe', status: 'applied', verified: true }
    const original = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'applied', receipt } })
    const undoCard = mount(KennRecipeCard, { props: { proposal: recipe, cardStatus: 'applied', receipt, undoable: false } })
    expect(original.find('.kenn-recipe-card__btn--undo').exists()).toBe(true)
    expect(undoCard.find('.kenn-recipe-card__btn--undo').exists()).toBe(false)
  })
})
